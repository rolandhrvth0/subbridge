# sb-nrview – DLSS 5 Game View worker (Linux, AMD RX 9000)

Built from these files plus the DLSSNR-AMD runtime (MIT, https://gitlab.com/mochizuki0323/DLSSNR-AMD):

    git clone https://gitlab.com/mochizuki0323/DLSSNR-AMD src && cd src && bash fetch_deps.sh
    source linux/build/arch/rdna4.sh
    python3 linux/build/build_network.py rdna4 --out "$NR_PRODUCT_SPV"     # shaders -> packaging/nr/dlssnr-amd/shaders
    C="-std=c++17 -O2 -DNDEBUG ${NR_PRODUCT_DEFINES[*]} -Itoolchain/Vulkan-Headers/include -Ilinux/src -Ilinux/src/core -Ilinux/src/layer -I<this dir>"
    g++ $C -c linux/src/core/nr_runtime.cpp linux/src/core/nr_native_plan.cpp <this dir>/sb_nrview.cpp
    g++ -o sb-nrview sb_nrview.o nr_runtime.o nr_native_plan.o -l:libvulkan.so.1 -l:libxcb.so.1 -lpthread

Nothing of NVIDIA's is in the repository or the packages: the user loads their own nvngx_dlssnr.dll in the app,
which extracts and verifies the network weights (packaging/nr/model-tools, from DLSSNR-AMD) into
~/.local/share/subbridge/nr/dlssnr-amd/. The DLL itself is never loaded or run.
