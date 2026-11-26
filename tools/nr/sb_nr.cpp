// SubBridge experiment: DLSS 5 neural rendering worker (DLSSNR-AMD runtime, Vulkan, AMD RDNA4).
//   sb-nr <root with dlssnr-amd/> <width> <height> <shm file>
// shm file: [in RGBA8 w*h*4][out RGBA8 w*h*4]. stdin: "f\n" = process in -> out, "q\n" = quit.
// stdout: "ready <build ms>\n" once, then "done <ms>\n" (or "err <text>\n") per frame.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/mman.h>
#include <unistd.h>
#include "nrvk.hpp"
#include "nr_runtime.hpp"

static void barrier(VkCommandBuffer cmd, VkImage img, VkImageLayout from, VkImageLayout to) {
    VkImageMemoryBarrier b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    b.srcAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
    b.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
    b.oldLayout = from; b.newLayout = to;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = img;
    b.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0,
                         0, nullptr, 0, nullptr, 1, &b);
}

// A host-visible buffer in CPU-cached memory: reading the answer back from write-combined memory (what a plain
// HOST_VISIBLE|HOST_COHERENT pick gives on RADV) costs ~50 ms for a 1440p picture; cached memory ~2 ms.
static nrvk::Buffer cached_buffer(nrvk::Context& ctx, VkDeviceSize bytes) {
    nrvk::Buffer b; b.bytes = bytes;
    VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    info.size = bytes;
    info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    NRVK_CHECK(vkCreateBuffer(ctx.device, &info, nullptr, &b.handle));
    VkMemoryRequirements req; vkGetBufferMemoryRequirements(ctx.device, b.handle, &req);
    const VkMemoryPropertyFlags want = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT;
    uint32_t type = ctx.mem.memoryTypeCount;
    for (uint32_t i = 0; i < ctx.mem.memoryTypeCount; ++i)
        if ((req.memoryTypeBits & (1u << i)) && (ctx.mem.memoryTypes[i].propertyFlags & want) == want) { type = i; break; }
    if (type == ctx.mem.memoryTypeCount) throw std::runtime_error("no host-cached memory type");
    VkMemoryAllocateInfo alloc{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    alloc.allocationSize = req.size; alloc.memoryTypeIndex = type;
    NRVK_CHECK(vkAllocateMemory(ctx.device, &alloc, nullptr, &b.memory));
    NRVK_CHECK(vkBindBufferMemory(ctx.device, b.handle, b.memory, 0));
    NRVK_CHECK(vkMapMemory(ctx.device, b.memory, 0, bytes, 0, &b.mapped));
    return b;
}

int main(int argc, char** argv) {
    if (argc < 5) { std::fprintf(stderr, "usage: sb-nr root w h shm\n"); return 2; }
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const uint32_t w = std::atoi(argv[2]), h = std::atoi(argv[3]);
    const size_t bytes = size_t(w) * h * 4;
    const int fd = open(argv[4], O_RDWR);
    if (fd < 0) { std::printf("err cannot open shm\n"); return 1; }
    auto* shm = static_cast<uint8_t*>(mmap(nullptr, bytes * 2, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
    if (shm == MAP_FAILED) { std::printf("err mmap\n"); return 1; }
    try {
        nrvk::Context ctx;
        ctx.create();
        nr::HostDevice host;
        host.instance = ctx.instance; host.physical = ctx.physical; host.device = ctx.device;
        host.queue = ctx.queue; host.queue_family = ctx.family;
        nr::RuntimeConfig cfg;
        cfg.root = argv[1]; cfg.width = w; cfg.height = h;
        cfg.colour_format = VK_FORMAT_R8G8B8A8_UNORM;
        cfg.network = 1;
        const auto t0 = std::chrono::steady_clock::now();
        // SB_TEMPORAL=1: the history path with the runtime's own motion estimate (no engine vectors on a video)
        const bool temporal = getenv("SB_TEMPORAL") && getenv("SB_TEMPORAL")[0] == '1';
        nr::TemporalConfig tc;
        tc.enable = temporal;
        tc.shaders = std::string(argv[1]) + "/dlssnr-amd/shaders/temporal";
        nr::Runtime rt(host, cfg, nr::ControlMaskConfig{}, tc);
        nr::TemporalFrame tf;
        bool first = true;
        const double build = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();

        auto img = ctx.image(w, h, VK_FORMAT_R8G8B8A8_UNORM, true);
        ctx.transition(img, VK_IMAGE_LAYOUT_GENERAL);
        auto stage = ctx.buffer(bytes, true);              // upload: host-visible (write-combined is fine for writes)
        auto back = cached_buffer(ctx, bytes);             // readback: CPU-cached
        nr::ColourFrame cf;
        cf.image = img.handle; cf.format = VK_FORMAT_R8G8B8A8_UNORM; cf.width = w; cf.height = h;
        cf.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_STORAGE_BIT |
                   VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        nr::Controls ctl;

        VkCommandPoolCreateInfo cpi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        cpi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        cpi.queueFamilyIndex = ctx.family;
        VkCommandPool pool; NRVK_CHECK(vkCreateCommandPool(ctx.device, &cpi, nullptr, &pool));
        VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        cai.commandPool = pool; cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount = 1;
        VkCommandBuffer cmd; NRVK_CHECK(vkAllocateCommandBuffers(ctx.device, &cai, &cmd));
        VkFenceCreateInfo fi{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        VkFence fence; NRVK_CHECK(vkCreateFence(ctx.device, &fi, nullptr, &fence));
        VkBufferImageCopy region{};
        region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        region.imageExtent = {w, h, 1};

        std::printf("ready %.0f\n", build);
        char line[96];
        while (std::fgets(line, sizeof line, stdin)) {
            if (line[0] == 'q') break;
            if (line[0] == 'c') {   // c <intensity> <style 0 std,1 natural,2 cinematic> <tone> <structure> <skin 0/1>
                float in = 1, tone = 1, st = 1; int sty = 0, skin = 0;
                if (std::sscanf(line + 1, "%f %d %f %f %d", &in, &sty, &tone, &st, &skin) >= 2) {
                    ctl.intensity = in; ctl.style = sty < 0 ? 0 : sty > 2 ? 2 : sty;
                    ctl.local_tone = tone; ctl.local_structure = st; ctl.skin_protection = skin != 0;
                    ctl.skin_detail = 0.0f; ctl.skin_colour = 0.35f;
                }
                std::printf("look\n");
                continue;
            }
            if (line[0] != 'f') continue;
            const auto a = std::chrono::steady_clock::now();
            std::memcpy(stage.mapped, shm, bytes);
            VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
            bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
            NRVK_CHECK(vkBeginCommandBuffer(cmd, &bi));
            barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
            vkCmdCopyBufferToImage(cmd, stage.handle, img.handle, VK_IMAGE_LAYOUT_GENERAL, 1, &region);
            barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
            if (temporal) {
                tf.reset = first;
                auto tr = rt.record_temporal(cmd, cf, ctl, tf);
                if (first) std::fprintf(stderr, "temporal: provider %s\n", tr.motion_provider);
                first = false;
            } else {
                rt.record(cmd, cf, ctl);
            }
            barrier(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL);
            vkCmdCopyImageToBuffer(cmd, img.handle, VK_IMAGE_LAYOUT_GENERAL, back.handle, 1, &region);
            VkBufferMemoryBarrier bb{VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER};
            bb.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; bb.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
            bb.srcQueueFamilyIndex = bb.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            bb.buffer = back.handle; bb.size = VK_WHOLE_SIZE;
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 0, nullptr,
                                 1, &bb, 0, nullptr);
            NRVK_CHECK(vkEndCommandBuffer(cmd));
            VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
            si.commandBufferCount = 1; si.pCommandBuffers = &cmd;
            ctx.submit(si, fence);
            NRVK_CHECK(vkWaitForFences(ctx.device, 1, &fence, VK_TRUE, 5000000000ull));
            NRVK_CHECK(vkResetFences(ctx.device, 1, &fence));
            NRVK_CHECK(vkResetCommandBuffer(cmd, 0));
            {   // harmless on coherent memory, required on non-coherent cached memory
                VkMappedMemoryRange r{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};
                r.memory = back.memory; r.size = VK_WHOLE_SIZE;
                vkInvalidateMappedMemoryRanges(ctx.device, 1, &r);
            }
            std::memcpy(shm + bytes, back.mapped, bytes);
            std::printf("done %.2f\n", std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - a).count());
        }
        vkDeviceWaitIdle(ctx.device);
        vkDestroyFence(ctx.device, fence, nullptr);
        vkDestroyCommandPool(ctx.device, pool, nullptr);
    } catch (const std::exception& e) {
        std::printf("err %s\n", e.what());
        return 1;
    }
    return 0;
}
