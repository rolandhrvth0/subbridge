// SubBridge experiment: GPU-only Game View with DLSS 5 neural rendering (DLSSNR-AMD runtime, AMD RDNA4, X11).
//   sb-nrview <root with dlssnr-amd/> <width> <height> <shm file> [neural 0/1]
// shm: two slots of NV12 (w*h*3/2 bytes each). stdin: "f <slot>\n" show that slot, "n 0|1\n" neural off/on,
// "q\n" quit. stdout: "ready <build ms>", "win <xid>", then "done <slot> <ms>" per frame, "closed" when the
// window is closed. The picture never comes back to the CPU: upload NV12 -> GPU convert -> NR -> blit -> present.
// Frame generation (lsfg-vk) attaches to this program's swapchain as a Vulkan layer.
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <string>
#include <sys/mman.h>
#include <sys/select.h>
#include <unistd.h>
#include <vector>
#include <xcb/xcb.h>
#define VK_USE_PLATFORM_XCB_KHR
#include <vulkan/vulkan.h>
#include "nrvk.hpp"
#include "nr_runtime.hpp"
#include "nv12_rgba.h"

#define CK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) throw std::runtime_error(std::string(#x) + " = " + std::to_string(r_)); } while (0)

static xcb_atom_t atom(xcb_connection_t* c, const char* name) {
    auto r = xcb_intern_atom_reply(c, xcb_intern_atom(c, 0, std::strlen(name), name), nullptr);
    xcb_atom_t a = r ? r->atom : 0; free(r); return a;
}

// Direct capture (SB_V4L2=/dev/videoN): the worker reads the card itself, so nothing in SubBridge's Python process
// (OCR, translation, GUI) can delay a frame. NV12, mmap buffers, newest frame wins. Every SB_SHARE_MS the frame
// is also copied (tightly packed) to shm slot 0 and "o 0" is printed: SubBridge reads its subtitles from that.
struct Card {
    int fd = -1; uint32_t w{}, h{}, bpl{}, fps{};
    struct B { void* p; size_t n; }; std::vector<B> bufs;
    std::string path;
    std::chrono::steady_clock::time_point last_frame, opened;
    static int xioctl(int fd, unsigned long r, void* a) { int e; do e = ioctl(fd, r, a); while (e < 0 && errno == EINTR); return e; }
    bool open_dev() {
        close_dev();
        fd = ::open(path.c_str(), O_RDWR | O_NONBLOCK);
        if (fd < 0) return false;
        v4l2_format f{}; f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        f.fmt.pix.width = w; f.fmt.pix.height = h; f.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12; f.fmt.pix.field = V4L2_FIELD_NONE;
        if (xioctl(fd, VIDIOC_S_FMT, &f) < 0 || f.fmt.pix.pixelformat != V4L2_PIX_FMT_NV12 || f.fmt.pix.width != w ||
            f.fmt.pix.height != h) { close_dev(); return false; }
        bpl = f.fmt.pix.bytesperline ? f.fmt.pix.bytesperline : w;
        v4l2_streamparm sp{}; sp.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        sp.parm.capture.timeperframe.numerator = 1; sp.parm.capture.timeperframe.denominator = fps;
        xioctl(fd, VIDIOC_S_PARM, &sp);
        v4l2_requestbuffers rb{}; rb.count = 4; rb.type = V4L2_BUF_TYPE_VIDEO_CAPTURE; rb.memory = V4L2_MEMORY_MMAP;
        if (xioctl(fd, VIDIOC_REQBUFS, &rb) < 0 || rb.count < 2) { close_dev(); return false; }
        for (uint32_t i = 0; i < rb.count; ++i) {
            v4l2_buffer b{}; b.type = rb.type; b.memory = V4L2_MEMORY_MMAP; b.index = i;
            if (xioctl(fd, VIDIOC_QUERYBUF, &b) < 0) { close_dev(); return false; }
            void* p = mmap(nullptr, b.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, b.m.offset);
            if (p == MAP_FAILED) { close_dev(); return false; }
            bufs.push_back({p, b.length});
            xioctl(fd, VIDIOC_QBUF, &b);
        }
        v4l2_buf_type t = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (xioctl(fd, VIDIOC_STREAMON, &t) < 0) { close_dev(); return false; }
        opened = last_frame = std::chrono::steady_clock::now();
        return true;
    }
    void close_dev() {
        if (fd >= 0) { v4l2_buf_type t = V4L2_BUF_TYPE_VIDEO_CAPTURE; xioctl(fd, VIDIOC_STREAMOFF, &t); }
        for (auto& b : bufs) munmap(b.p, b.n);
        bufs.clear();
        if (fd >= 0) ::close(fd);
        fd = -1;
    }
    // newest complete frame copied (tight NV12) into dst; returns false if none was waiting
    bool grab(uint8_t* dst) {
        v4l2_buffer b{}, got{}; bool have = false;
        for (;;) {
            b = {}; b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE; b.memory = V4L2_MEMORY_MMAP;
            if (xioctl(fd, VIDIOC_DQBUF, &b) < 0) break;
            if (have) xioctl(fd, VIDIOC_QBUF, &got);          // an older one: give it straight back
            got = b; have = true;
        }
        if (!have) return false;
        const uint8_t* src = static_cast<const uint8_t*>(bufs[got.index].p);
        const bool ok = !(got.flags & V4L2_BUF_FLAG_ERROR) && got.bytesused >= size_t(bpl) * h * 3 / 2;
        if (ok) {
            if (bpl == w) std::memcpy(dst, src, size_t(w) * h * 3 / 2);
            else for (uint32_t y = 0; y < h * 3 / 2; ++y) std::memcpy(dst + size_t(y) * w, src + size_t(y) * bpl, w);
            last_frame = std::chrono::steady_clock::now();
        }
        xioctl(fd, VIDIOC_QBUF, &got);
        return ok;
    }
};

struct App {
    // window
    xcb_connection_t* xc{}; xcb_window_t win{}; xcb_atom_t wm_delete{}, wm_state{}, wm_full{};
    bool fullscreen = false;
    // vulkan
    VkInstance inst{}; VkPhysicalDevice phys{}; VkDevice dev{}; VkQueue queue{}; uint32_t family{};
    VkSurfaceKHR surface{}; VkSwapchainKHR swap{}; VkFormat swap_fmt{}; VkExtent2D swap_ext{};
    std::vector<VkImage> swap_imgs;
    nrvk::Context ctx;
    uint32_t w{}, h{}; size_t slot_bytes{};
    uint8_t* shm{};

    void create_window() {
        xc = xcb_connect(nullptr, nullptr);
        if (xcb_connection_has_error(xc)) throw std::runtime_error("cannot open X display");
        xcb_screen_t* s = xcb_setup_roots_iterator(xcb_get_setup(xc)).data;
        win = xcb_generate_id(xc);
        uint32_t mask = XCB_CW_BACK_PIXEL | XCB_CW_EVENT_MASK;
        uint32_t vals[] = {s->black_pixel, XCB_EVENT_MASK_KEY_PRESS | XCB_EVENT_MASK_STRUCTURE_NOTIFY |
                                           XCB_EVENT_MASK_BUTTON_PRESS};
        xcb_create_window(xc, XCB_COPY_FROM_PARENT, win, s->root, 0, 0, 1280, 720, 0,
                          XCB_WINDOW_CLASS_INPUT_OUTPUT, s->root_visual, mask, vals);
        const char* title = "SubBridge – Játéknézet (DLSS 5)";
        xcb_change_property(xc, XCB_PROP_MODE_REPLACE, win, atom(xc, "_NET_WM_NAME"), atom(xc, "UTF8_STRING"), 8,
                            std::strlen(title), title);
        const char cls[] = "sb-nrview\0SubBridge";
        xcb_change_property(xc, XCB_PROP_MODE_REPLACE, win, XCB_ATOM_WM_CLASS, XCB_ATOM_STRING, 8, sizeof cls, cls);
        wm_delete = atom(xc, "WM_DELETE_WINDOW");
        xcb_change_property(xc, XCB_PROP_MODE_REPLACE, win, atom(xc, "WM_PROTOCOLS"), XCB_ATOM_ATOM, 32, 1, &wm_delete);
        wm_state = atom(xc, "_NET_WM_STATE"); wm_full = atom(xc, "_NET_WM_STATE_FULLSCREEN");
        xcb_map_window(xc, win);
        xcb_flush(xc);
    }

    void set_fullscreen(bool on) {
        fullscreen = on;
        xcb_screen_t* s = xcb_setup_roots_iterator(xcb_get_setup(xc)).data;
        xcb_client_message_event_t ev{};
        ev.response_type = XCB_CLIENT_MESSAGE; ev.format = 32; ev.window = win; ev.type = wm_state;
        ev.data.data32[0] = on ? 1 : 0; ev.data.data32[1] = wm_full; ev.data.data32[3] = 1;
        xcb_send_event(xc, 0, s->root, XCB_EVENT_MASK_SUBSTRUCTURE_REDIRECT | XCB_EVENT_MASK_SUBSTRUCTURE_NOTIFY,
                       reinterpret_cast<const char*>(&ev));
        xcb_flush(xc);
    }

    // The device: what nrvk::Context::create enables for the network, plus surface/swapchain for presenting.
    void create_device() {
        const char* iexts[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_XCB_SURFACE_EXTENSION_NAME};
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "sb-nrview"; app.apiVersion = VK_API_VERSION_1_3;
        VkInstanceCreateInfo ii{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        ii.pApplicationInfo = &app; ii.enabledExtensionCount = 2; ii.ppEnabledExtensionNames = iexts;
        CK(vkCreateInstance(&ii, nullptr, &inst));
        VkXcbSurfaceCreateInfoKHR si{VK_STRUCTURE_TYPE_XCB_SURFACE_CREATE_INFO_KHR};
        si.connection = xc; si.window = win;
        CK(vkCreateXcbSurfaceKHR(inst, &si, nullptr, &surface));
        uint32_t n = 0; vkEnumeratePhysicalDevices(inst, &n, nullptr);
        std::vector<VkPhysicalDevice> devs(n); vkEnumeratePhysicalDevices(inst, &n, devs.data());
        for (auto d : devs) {
            VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(d, &p);
            if (p.vendorID == 0x1002 && p.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) { phys = d; break; }
        }
        if (!phys) throw std::runtime_error("no AMD discrete GPU");
        uint32_t qn = 0; vkGetPhysicalDeviceQueueFamilyProperties(phys, &qn, nullptr);
        std::vector<VkQueueFamilyProperties> qs(qn); vkGetPhysicalDeviceQueueFamilyProperties(phys, &qn, qs.data());
        family = qn;
        for (uint32_t i = 0; i < qn; ++i) {
            VkBool32 present = VK_FALSE; vkGetPhysicalDeviceSurfaceSupportKHR(phys, i, surface, &present);
            if ((qs[i].queueFlags & VK_QUEUE_COMPUTE_BIT) && (qs[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) && present) {
                family = i; break;
            }
        }
        if (family == qn) throw std::runtime_error("no queue that computes and presents");

        VkPhysicalDeviceCooperativeMatrixFeaturesKHR coop{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
        coop.cooperativeMatrix = VK_TRUE;
        VkPhysicalDeviceShaderFloat8FeaturesEXT fp8{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_FLOAT8_FEATURES_EXT};
        fp8.shaderFloat8 = VK_TRUE; fp8.shaderFloat8CooperativeMatrix = VK_TRUE;
        VkPhysicalDeviceVulkan11Features f11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES};
        f11.storageBuffer16BitAccess = VK_TRUE;
        VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
        f12.storageBuffer8BitAccess = VK_TRUE; f12.shaderFloat16 = VK_TRUE; f12.shaderInt8 = VK_TRUE;
        f12.vulkanMemoryModel = VK_TRUE;
        VkPhysicalDeviceVulkan13Features f13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
        f13.subgroupSizeControl = VK_TRUE; f13.synchronization2 = VK_TRUE;
        VkPhysicalDeviceWorkgroupMemoryExplicitLayoutFeaturesKHR wml{
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_WORKGROUP_MEMORY_EXPLICIT_LAYOUT_FEATURES_KHR};
        {   VkPhysicalDeviceFeatures2 q{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2}; q.pNext = &wml;
            vkGetPhysicalDeviceFeatures2(phys, &q); }
        const bool have_wml = wml.workgroupMemoryExplicitLayout && wml.workgroupMemoryExplicitLayout8BitAccess &&
                              wml.workgroupMemoryExplicitLayout16BitAccess;
        wml.pNext = nullptr; wml.workgroupMemoryExplicitLayoutScalarBlockLayout = VK_FALSE;
        VkPhysicalDevicePipelineRobustnessFeaturesEXT prf{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_ROBUSTNESS_FEATURES_EXT};
        prf.pipelineRobustness = VK_TRUE;
        coop.pNext = &fp8; fp8.pNext = &f11; f11.pNext = &f12; f12.pNext = &f13;
        f13.pNext = have_wml ? static_cast<void*>(&wml) : static_cast<void*>(&prf);
        if (have_wml) wml.pNext = &prf;
        std::vector<const char*> dexts = {VK_KHR_COOPERATIVE_MATRIX_EXTENSION_NAME, VK_EXT_SHADER_FLOAT8_EXTENSION_NAME,
                                          VK_EXT_PIPELINE_ROBUSTNESS_EXTENSION_NAME, VK_KHR_SWAPCHAIN_EXTENSION_NAME};
        if (have_wml) dexts.push_back(VK_KHR_WORKGROUP_MEMORY_EXPLICIT_LAYOUT_EXTENSION_NAME);
        float prio = 1.0f;
        VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        qi.queueFamilyIndex = family; qi.queueCount = 1; qi.pQueuePriorities = &prio;
        VkDeviceCreateInfo di{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        di.pNext = &coop; di.queueCreateInfoCount = 1; di.pQueueCreateInfos = &qi;
        di.enabledExtensionCount = uint32_t(dexts.size()); di.ppEnabledExtensionNames = dexts.data();
        CK(vkCreateDevice(phys, &di, nullptr, &dev));
        vkGetDeviceQueue(dev, family, 0, &queue);
        std::string why;
        if (!ctx.adopt(inst, phys, dev, queue, family, &why)) throw std::runtime_error("adopt: " + why);
    }

    void create_swapchain() {
        VkSurfaceCapabilitiesKHR caps; CK(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(phys, surface, &caps));
        uint32_t n = 0; vkGetPhysicalDeviceSurfaceFormatsKHR(phys, surface, &n, nullptr);
        std::vector<VkSurfaceFormatKHR> fmts(n); vkGetPhysicalDeviceSurfaceFormatsKHR(phys, surface, &n, fmts.data());
        VkSurfaceFormatKHR f = fmts[0];
        for (auto& x : fmts) if (x.format == VK_FORMAT_B8G8R8A8_UNORM) { f = x; break; }
        swap_fmt = f.format;
        swap_ext = caps.currentExtent.width != 0xFFFFFFFFu ? caps.currentExtent : VkExtent2D{1280, 720};
        if (!swap_ext.width || !swap_ext.height) return;            // minimised
        VkSwapchainCreateInfoKHR ci{VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR};
        ci.surface = surface; ci.minImageCount = std::max(caps.minImageCount, 2u);   // shortest queue: least latency
        if (caps.maxImageCount) ci.minImageCount = std::min(ci.minImageCount, caps.maxImageCount);
        ci.imageFormat = f.format; ci.imageColorSpace = f.colorSpace; ci.imageExtent = swap_ext;
        ci.imageArrayLayers = 1; ci.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
        ci.preTransform = caps.currentTransform; ci.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        ci.presentMode = VK_PRESENT_MODE_FIFO_KHR;                  // lsfg-vk paces its own frames
        ci.clipped = VK_TRUE; ci.oldSwapchain = swap;
        VkSwapchainKHR ns; CK(vkCreateSwapchainKHR(dev, &ci, nullptr, &ns));
        if (swap) vkDestroySwapchainKHR(dev, swap, nullptr);
        swap = ns;
        vkGetSwapchainImagesKHR(dev, swap, &n, nullptr); swap_imgs.resize(n);
        vkGetSwapchainImagesKHR(dev, swap, &n, swap_imgs.data());
    }
};

static void image_barrier(VkCommandBuffer cmd, VkImage img, VkImageLayout from, VkImageLayout to) {
    VkImageMemoryBarrier b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    b.srcAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
    b.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
    b.oldLayout = from; b.newLayout = to;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = img; b.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr,
                         0, nullptr, 1, &b);
}

// sb-nrview --probe: can this PC run the network? Prints "ok <gpu> | <driver>" or "no <reason>" and exits.
static int probe() {
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "sb-nrview-probe"; app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ii{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ii.pApplicationInfo = &app;
    VkInstance inst;
    if (vkCreateInstance(&ii, nullptr, &inst) != VK_SUCCESS) { std::printf("no Vulkan\n"); return 1; }
    uint32_t n = 0; vkEnumeratePhysicalDevices(inst, &n, nullptr);
    std::vector<VkPhysicalDevice> devs(n); vkEnumeratePhysicalDevices(inst, &n, devs.data());
    std::string why = "no AMD graphics card";
    for (auto d : devs) {
        VkPhysicalDeviceDriverProperties drv{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
        VkPhysicalDeviceProperties2 pr{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2}; pr.pNext = &drv;
        vkGetPhysicalDeviceProperties2(d, &pr);
        if (pr.properties.vendorID != 0x1002 || pr.properties.deviceType != VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) continue;
        VkPhysicalDeviceCooperativeMatrixFeaturesKHR coop{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
        VkPhysicalDeviceShaderFloat8FeaturesEXT fp8{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_FLOAT8_FEATURES_EXT};
        coop.pNext = &fp8;
        VkPhysicalDeviceFeatures2 f{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2}; f.pNext = &coop;
        vkGetPhysicalDeviceFeatures2(d, &f);
        if (!coop.cooperativeMatrix || !fp8.shaderFloat8 || !fp8.shaderFloat8CooperativeMatrix) {
            why = std::string(pr.properties.deviceName) + ": no FP8 matrix support (needs an RX 9000 card and Mesa 26.2+)";
            continue;
        }
        std::printf("ok %s | %s %s\n", pr.properties.deviceName, drv.driverName, drv.driverInfo);
        vkDestroyInstance(inst, nullptr);
        return 0;
    }
    std::printf("no %s\n", why.c_str());
    vkDestroyInstance(inst, nullptr);
    return 1;
}

int main(int argc, char** argv) {
    if (argc >= 2 && std::string(argv[1]) == "--probe") return probe();
    if (argc < 5) { std::fprintf(stderr, "usage: sb-nrview root w h shm [neural] | --probe\n"); return 2; }
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    App a;
    a.w = std::atoi(argv[2]); a.h = std::atoi(argv[3]);
    bool neural = argc > 5 ? std::atoi(argv[5]) != 0 : true;
    a.slot_bytes = size_t(a.w) * a.h * 3 / 2;
    const int fd = open(argv[4], O_RDWR);
    if (fd < 0) { std::printf("err cannot open shm\n"); return 1; }
    a.shm = static_cast<uint8_t*>(mmap(nullptr, a.slot_bytes * 2, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
    if (a.shm == MAP_FAILED) { std::printf("err mmap\n"); return 1; }
    try {
        a.create_window();
        a.create_device();
        a.create_swapchain();
        nr::HostDevice host;
        host.instance = a.inst; host.physical = a.phys; host.device = a.dev; host.queue = a.queue;
        host.queue_family = a.family;
        nr::RuntimeConfig cfg;
        cfg.root = argv[1]; cfg.width = a.w; cfg.height = a.h; cfg.colour_format = VK_FORMAT_R8G8B8A8_UNORM;
        cfg.network = 1;
        const auto t0 = std::chrono::steady_clock::now();
        // the history path with the runtime's own motion estimate: frame-to-frame stable (no flicker); a video
        // has no engine motion vectors. SB_TEMPORAL=0 switches back to independent frames.
        const bool temporal = !(getenv("SB_TEMPORAL") && getenv("SB_TEMPORAL")[0] == '0');
        nr::TemporalConfig tc;
        tc.enable = temporal;
        tc.shaders = std::string(argv[1]) + "/dlssnr-amd/shaders/temporal";
        nr::Runtime rt(host, cfg, nr::ControlMaskConfig{}, tc);
        nr::TemporalFrame tf;
        bool first_frame = true;
        const double build = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        auto& ctx = a.ctx;

        // resources
        auto img = ctx.image(a.w, a.h, VK_FORMAT_R8G8B8A8_UNORM, true);
        ctx.transition(img, VK_IMAGE_LAYOUT_GENERAL);
        nrvk::Buffer stage[2] = {ctx.buffer(a.slot_bytes, true), ctx.buffer(a.slot_bytes, true)};
        nr::ColourFrame cf;
        cf.image = img.handle; cf.format = VK_FORMAT_R8G8B8A8_UNORM; cf.width = a.w; cf.height = a.h;
        cf.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                   VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        nr::Controls ctl;

        // NV12 -> RGBA pipeline
        VkDescriptorSetLayoutBinding binds[2] = {
            {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
            {1, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}};
        VkDescriptorSetLayoutCreateInfo dl{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        dl.bindingCount = 2; dl.pBindings = binds;
        VkDescriptorSetLayout dsl; CK(vkCreateDescriptorSetLayout(a.dev, &dl, nullptr, &dsl));
        VkPushConstantRange pcr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 16};
        VkPipelineLayoutCreateInfo pl{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        pl.setLayoutCount = 1; pl.pSetLayouts = &dsl; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &pcr;
        VkPipelineLayout layout; CK(vkCreatePipelineLayout(a.dev, &pl, nullptr, &layout));
        VkShaderModuleCreateInfo sm{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        sm.codeSize = sizeof nv12_rgba_spv; sm.pCode = nv12_rgba_spv;
        VkShaderModule mod; CK(vkCreateShaderModule(a.dev, &sm, nullptr, &mod));
        VkComputePipelineCreateInfo cp{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        cp.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_COMPUTE_BIT, mod,
                    "main", nullptr};
        cp.layout = layout;
        VkPipeline conv; CK(vkCreateComputePipelines(a.dev, VK_NULL_HANDLE, 1, &cp, nullptr, &conv));
        VkDescriptorPoolSize ps[2] = {{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2}, {VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 2}};
        VkDescriptorPoolCreateInfo dp{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        dp.maxSets = 2; dp.poolSizeCount = 2; dp.pPoolSizes = ps;
        VkDescriptorPool pool_d; CK(vkCreateDescriptorPool(a.dev, &dp, nullptr, &pool_d));
        VkDescriptorSet sets[2];
        VkDescriptorSetLayout dsls[2] = {dsl, dsl};
        VkDescriptorSetAllocateInfo da{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        da.descriptorPool = pool_d; da.descriptorSetCount = 2; da.pSetLayouts = dsls;
        CK(vkAllocateDescriptorSets(a.dev, &da, sets));
        VkImageViewCreateInfo vi{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        vi.image = img.handle; vi.viewType = VK_IMAGE_VIEW_TYPE_2D; vi.format = VK_FORMAT_R8G8B8A8_UNORM;
        vi.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        VkImageView view; CK(vkCreateImageView(a.dev, &vi, nullptr, &view));
        for (int i = 0; i < 2; ++i) {
            VkDescriptorBufferInfo bi{stage[i].handle, 0, VK_WHOLE_SIZE};
            VkDescriptorImageInfo ii{VK_NULL_HANDLE, view, VK_IMAGE_LAYOUT_GENERAL};
            VkWriteDescriptorSet wr[2] = {{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET}, {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET}};
            wr[0].dstSet = sets[i]; wr[0].dstBinding = 0; wr[0].descriptorCount = 1;
            wr[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr[0].pBufferInfo = &bi;
            wr[1].dstSet = sets[i]; wr[1].dstBinding = 1; wr[1].descriptorCount = 1;
            wr[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; wr[1].pImageInfo = &ii;
            vkUpdateDescriptorSets(a.dev, 2, wr, 0, nullptr);
        }

        // per-frame objects
        VkCommandPoolCreateInfo cpi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; cpi.queueFamilyIndex = a.family;
        VkCommandPool cpool; CK(vkCreateCommandPool(a.dev, &cpi, nullptr, &cpool));
        VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        cai.commandPool = cpool; cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount = 1;
        VkCommandBuffer cmd; CK(vkAllocateCommandBuffers(a.dev, &cai, &cmd));
        VkFenceCreateInfo fci{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        VkFence fence; CK(vkCreateFence(a.dev, &fci, nullptr, &fence));
        VkSemaphoreCreateInfo sci{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
        VkSemaphore acquired, rendered;
        CK(vkCreateSemaphore(a.dev, &sci, nullptr, &acquired)); CK(vkCreateSemaphore(a.dev, &sci, nullptr, &rendered));

        std::printf("ready %.0f\n", build);
        std::printf("win %u\n", a.win);
        bool running = true, have_frame = false, fresh_look = false;
        int last_slot = 0;
        std::string inbuf;
        auto draw = [&](int slot, bool fresh) {
            if (!a.swap || a.swap_imgs.empty()) return;
            const auto t = std::chrono::steady_clock::now();
            uint32_t idx;
            VkResult r = vkAcquireNextImageKHR(a.dev, a.swap, 1000000000ull, acquired, VK_NULL_HANDLE, &idx);
            if (r == VK_ERROR_OUT_OF_DATE_KHR) { vkDeviceWaitIdle(a.dev); a.create_swapchain(); return; }
            VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
            bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
            CK(vkBeginCommandBuffer(cmd, &bi));
            if (fresh) {
                image_barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
                vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, conv);
                vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 1, &sets[slot], 0, nullptr);
                uint32_t pc[4] = {a.w, a.h, 0, 0};
                vkCmdPushConstants(cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, 16, pc);
                vkCmdDispatch(cmd, (a.w + 15) / 16, (a.h + 15) / 16, 1);
                image_barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
                if (neural && temporal) {
                    tf.reset = first_frame;
                    rt.record_temporal(cmd, cf, ctl, tf);
                    first_frame = false;
                } else if (neural) {
                    rt.record(cmd, cf, ctl);
                } else {
                    first_frame = true;               // NR off: the history restarts when it comes back
                }
                image_barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
            }
            VkImage dst = a.swap_imgs[idx];
            image_barrier(cmd, dst, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
            VkClearColorValue black{}; VkImageSubresourceRange rng{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
            vkCmdClearColorImage(cmd, dst, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &black, 1, &rng);
            // letterbox: keep the picture's aspect, centred
            const float s = std::min(float(a.swap_ext.width) / a.w, float(a.swap_ext.height) / a.h);
            const int dw = int(a.w * s), dh = int(a.h * s);
            const int ox = (int(a.swap_ext.width) - dw) / 2, oy = (int(a.swap_ext.height) - dh) / 2;
            VkImageBlit blit{};
            blit.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            blit.srcOffsets[1] = {int(a.w), int(a.h), 1};
            blit.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            blit.dstOffsets[0] = {ox, oy, 0}; blit.dstOffsets[1] = {ox + dw, oy + dh, 1};
            vkCmdBlitImage(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, dst, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &blit,
                           VK_FILTER_LINEAR);
            image_barrier(cmd, dst, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR);
            CK(vkEndCommandBuffer(cmd));
            VkPipelineStageFlags wait = VK_PIPELINE_STAGE_TRANSFER_BIT;
            VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
            si.waitSemaphoreCount = 1; si.pWaitSemaphores = &acquired; si.pWaitDstStageMask = &wait;
            si.commandBufferCount = 1; si.pCommandBuffers = &cmd;
            si.signalSemaphoreCount = 1; si.pSignalSemaphores = &rendered;
            CK(vkQueueSubmit(a.queue, 1, &si, fence));
            VkPresentInfoKHR pi{VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};
            pi.waitSemaphoreCount = 1; pi.pWaitSemaphores = &rendered;
            pi.swapchainCount = 1; pi.pSwapchains = &a.swap; pi.pImageIndices = &idx;
            r = vkQueuePresentKHR(a.queue, &pi);
            CK(vkWaitForFences(a.dev, 1, &fence, VK_TRUE, 5000000000ull));
            CK(vkResetFences(a.dev, 1, &fence));
            CK(vkResetCommandBuffer(cmd, 0));
            if (r == VK_ERROR_OUT_OF_DATE_KHR || r == VK_SUBOPTIMAL_KHR) { vkDeviceWaitIdle(a.dev); a.create_swapchain(); }
            if (fresh)
                std::printf("done %d %.2f\n", slot,
                            std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count());
        };

        const int xfd = xcb_get_file_descriptor(a.xc);
        Card card;
        const char* dev = getenv("SB_V4L2");
        const bool direct = dev && *dev;
        const int share_ms = getenv("SB_SHARE_MS") ? std::max(20, std::atoi(getenv("SB_SHARE_MS"))) : 66;
        int share_slot = 0, cur = 0, reopen_tries = 0;
        unsigned long long seq = 0;
        auto last_share = std::chrono::steady_clock::now(), last_try = last_share;
        bool stalled_said = false;
        if (direct) {
            card.path = dev; card.w = a.w; card.h = a.h;
            card.fps = getenv("SB_V4L2_FPS") ? std::max(1, std::atoi(getenv("SB_V4L2_FPS"))) : 30;
            std::printf(card.open_dev() ? "card %u %u %u\n" : "nocard\n", card.w, card.h, card.fps);
        }
        while (running) {
            fd_set rd; FD_ZERO(&rd); FD_SET(0, &rd); FD_SET(xfd, &rd);
            int maxfd = xfd;
            if (card.fd >= 0) { FD_SET(card.fd, &rd); maxfd = std::max(maxfd, card.fd); }
            timeval tv{0, direct ? 100000 : 200000};
            select(maxfd + 1, &rd, nullptr, nullptr, &tv);
            bool redraw = false;
            if (direct) {
                const auto now = std::chrono::steady_clock::now();
                if (card.fd >= 0 && FD_ISSET(card.fd, &rd)) {
                    const int slot = cur ^ 1;
                    if (card.grab(static_cast<uint8_t*>(stage[slot].mapped))) {
                        reopen_tries = 0;
                        if (stalled_said) { std::printf("card ok\n"); stalled_said = false; }
                        // a 60 Hz signal: show every second picture – an even 30 fps cadence (the network's budget)
                        if (card.fps <= 40 || (seq++ & 1) == 0) {
                            cur = slot; last_slot = slot; have_frame = true;
                            if (std::chrono::duration<double, std::milli>(now - last_share).count() >= share_ms) {
                                share_slot ^= 1;
                                std::memcpy(a.shm + a.slot_bytes * share_slot, stage[slot].mapped, a.slot_bytes);
                                std::printf("o %d\n", share_slot);
                                last_share = now;
                            }
                            draw(slot, true);
                        }
                    }
                }
                // no picture for 4 s (console asleep, resolution change, USB reset): reopen, backing off
                const double idle = std::chrono::duration<double>(now - card.last_frame).count();
                const double since = std::chrono::duration<double>(now - last_try).count();
                if ((card.fd < 0 || idle > 4.0) && since > (reopen_tries < 3 ? 4.0 : 20.0)) {
                    if (!stalled_said) { std::printf("stall\n"); stalled_said = true; }
                    last_try = now; ++reopen_tries;
                    if (card.open_dev()) std::printf("card %u %u %u\n", card.w, card.h, card.fps);
                }
            }
            while (xcb_generic_event_t* ev = xcb_poll_for_event(a.xc)) {
                switch (ev->response_type & 0x7f) {
                case XCB_CLIENT_MESSAGE:
                    if (reinterpret_cast<xcb_client_message_event_t*>(ev)->data.data32[0] == a.wm_delete) running = false;
                    break;
                case XCB_KEY_PRESS: {
                    auto* k = reinterpret_cast<xcb_key_press_event_t*>(ev);
                    if (k->detail == 95 || k->detail == 41) a.set_fullscreen(!a.fullscreen);       // F11 / f
                    else if (k->detail == 9 && a.fullscreen) a.set_fullscreen(false);           // Esc
                    break; }
                case XCB_BUTTON_PRESS: break;
                case XCB_CONFIGURE_NOTIFY: {
                    auto* c = reinterpret_cast<xcb_configure_notify_event_t*>(ev);
                    if (c->width != a.swap_ext.width || c->height != a.swap_ext.height) {
                        vkDeviceWaitIdle(a.dev); a.create_swapchain(); redraw = true;
                    }
                    std::printf("geom\n");
                    break; }
                }
                free(ev);
            }
            if (xcb_connection_has_error(a.xc)) break;
            if (FD_ISSET(0, &rd)) {
                char buf[256]; ssize_t n = read(0, buf, sizeof buf);
                if (n <= 0) break;
                inbuf.append(buf, n);
                size_t nl;
                int want = -1;
                while ((nl = inbuf.find('\n')) != std::string::npos) {
                    std::string line = inbuf.substr(0, nl); inbuf.erase(0, nl + 1);
                    if (line[0] == 'q') running = false;
                    else if (line[0] == 'n' && line.size() > 2) neural = line[2] == '1';
                    else if (line[0] == 'c') {   // c <intensity> <style 0 std,1 natural,2 cinematic> <tone> <structure> <skin 0/1>
                        float in = 1, tone = 1, st = 1; int sty = 0, skin = 0;
                        if (std::sscanf(line.c_str() + 1, "%f %d %f %f %d", &in, &sty, &tone, &st, &skin) >= 2) {
                            ctl.intensity = in; ctl.style = std::clamp(sty, 0, 2);
                            ctl.local_tone = tone; ctl.local_structure = st;
                            ctl.skin_protection = skin != 0;
                            ctl.skin_detail = 0.0f; ctl.skin_colour = 0.35f;   // faces: keep the game's own detail
                            std::printf("look %.2f %d %.2f %.2f %d\n", in, ctl.style, tone, st, skin);
                            redraw = have_frame;
                            if (redraw) { fresh_look = true; }
                        }
                    }
                    else if (line[0] == 'f' && line.size() > 2) want = std::atoi(line.c_str() + 2) & 1;
                }
                if (want >= 0 && running) {
                    std::memcpy(stage[want].mapped, a.shm + a.slot_bytes * want, a.slot_bytes);
                    last_slot = want; have_frame = true;
                    draw(want, true);
                    redraw = false;
                }
            }
            if (redraw && have_frame) { draw(last_slot, fresh_look); fresh_look = false; }
        }
        card.close_dev();
        std::printf("closed\n");
        vkDeviceWaitIdle(a.dev);
    } catch (const std::exception& e) {
        std::printf("err %s\n", e.what());
        return 1;
    }
    return 0;
}
