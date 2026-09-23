#include <hsa/hsa.h>
#include <hsa/hsa_ext_amd.h>

#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <unistd.h>

#define HSA_OK(call) do { hsa_status_t s_ = (call); if(s_ != HSA_STATUS_SUCCESS) { \
  const char* m_ = nullptr; hsa_status_string(s_, &m_); \
  std::fprintf(stderr, "FAIL:HSA:%s:%d:%s => %d (%s)\n", __FILE__, __LINE__, #call, (int)s_, m_ ? m_ : "?"); \
  std::exit(2); } } while(0)

struct State {
  hsa_agent_t gpu{};
  hsa_agent_t cpu{};
  hsa_amd_memory_pool_t pool{};
  bool have_gpu = false;
  bool have_cpu = false;
  bool have_pool = false;
  int pool_score = -1;
};

static hsa_status_t find_agent(hsa_agent_t agent, void* p) {
  auto& s = *static_cast<State*>(p);
  hsa_device_type_t type{};
  HSA_OK(hsa_agent_get_info(agent, HSA_AGENT_INFO_DEVICE, &type));
  if(type == HSA_DEVICE_TYPE_GPU && !s.have_gpu) { s.gpu = agent; s.have_gpu = true; }
  if(type == HSA_DEVICE_TYPE_CPU && !s.have_cpu) { s.cpu = agent; s.have_cpu = true; }
  return HSA_STATUS_SUCCESS;
}
static hsa_status_t find_pool(hsa_amd_memory_pool_t pool, void* p) {
  auto& s = *static_cast<State*>(p);
  hsa_amd_segment_t seg{}; bool alloc = false; uint32_t flags = 0;
  HSA_OK(hsa_amd_memory_pool_get_info(pool, HSA_AMD_MEMORY_POOL_INFO_SEGMENT, &seg));
  HSA_OK(hsa_amd_memory_pool_get_info(pool, HSA_AMD_MEMORY_POOL_INFO_RUNTIME_ALLOC_ALLOWED, &alloc));
  if(seg != HSA_AMD_SEGMENT_GLOBAL || !alloc) return HSA_STATUS_SUCCESS;
  HSA_OK(hsa_amd_memory_pool_get_info(pool, HSA_AMD_MEMORY_POOL_INFO_GLOBAL_FLAGS, &flags));
  const int score = (flags & HSA_AMD_MEMORY_POOL_GLOBAL_FLAG_KERNARG_INIT) ? 2 :
                    ((flags & HSA_AMD_MEMORY_POOL_GLOBAL_FLAG_FINE_GRAINED) ? 1 : 0);
  if(score > s.pool_score) { s.pool = pool; s.have_pool = true; s.pool_score = score; }
  return HSA_STATUS_SUCCESS;
}

static void* alloc_shared(State& s, size_t n) {
  void* p = nullptr;
  HSA_OK(hsa_amd_memory_pool_allocate(s.pool, n, 0, &p));
  HSA_OK(hsa_amd_agents_allow_access(1, &s.gpu, nullptr, p));
  return p;
}

struct KernelInfo { uint64_t object = 0; uint32_t group = 0; uint32_t priv = 0; uint32_t kernarg = 0; };
static hsa_status_t find_symbol(hsa_executable_t, hsa_agent_t, hsa_executable_symbol_t sym, void* p) {
  hsa_symbol_kind_t kind{};
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_TYPE, &kind));
  if(kind != HSA_SYMBOL_KIND_KERNEL) return HSA_STATUS_SUCCESS;
  uint32_t len = 0;
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_NAME_LENGTH, &len));
  std::string name(len, '\0');
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_NAME, name.data()));
  if(name.find("fixture_vector_add") == std::string::npos) return HSA_STATUS_SUCCESS;
  auto& k = *static_cast<KernelInfo*>(p);
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_KERNEL_OBJECT, &k.object));
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_KERNEL_GROUP_SEGMENT_SIZE, &k.group));
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_KERNEL_PRIVATE_SEGMENT_SIZE, &k.priv));
  HSA_OK(hsa_executable_symbol_get_info(sym, HSA_EXECUTABLE_SYMBOL_INFO_KERNEL_KERNARG_SEGMENT_SIZE, &k.kernarg));
  return HSA_STATUS_SUCCESS;
}

static void publish_header(void* packet, uint16_t header) {
  __atomic_store_n(static_cast<uint16_t*>(packet), header, __ATOMIC_RELEASE);
}
static uint16_t header(hsa_packet_type_t type, bool barrier) {
  return uint16_t((uint16_t(type) << HSA_PACKET_HEADER_TYPE) |
                  (uint16_t(barrier) << HSA_PACKET_HEADER_BARRIER) |
                  (uint16_t(HSA_FENCE_SCOPE_SYSTEM) << HSA_PACKET_HEADER_SCACQUIRE_FENCE_SCOPE) |
                  (uint16_t(HSA_FENCE_SCOPE_SYSTEM) << HSA_PACKET_HEADER_SCRELEASE_FENCE_SCOPE));
}
static void wait_zero(hsa_signal_t sig, const char* label) {
  std::printf("STAGE:wait:%s\n", label); std::fflush(stdout);
  const auto v = hsa_signal_wait_scacquire(sig, HSA_SIGNAL_CONDITION_EQ, 0, UINT64_MAX, HSA_WAIT_STATE_BLOCKED);
  if(v != 0) { std::fprintf(stderr, "FAIL:signal:%s:%lld\n", label, (long long)v); std::exit(3); }
  std::printf("STAGE:complete:%s\n", label); std::fflush(stdout);
}

int main(int argc, char** argv) {
  if(argc != 3 || (std::strcmp(argv[1], "control") && std::strcmp(argv[1], "mixed"))) {
    std::fprintf(stderr, "usage: %s {control|mixed} CODE_OBJECT\n", argv[0]); return 64;
  }
  const bool mixed = std::strcmp(argv[1], "mixed") == 0;
  std::printf("STAGE:init mode=%s nonkernel_packets=%d\n", argv[1], mixed ? 1 : 0); std::fflush(stdout);
  HSA_OK(hsa_init());
  State s; HSA_OK(hsa_iterate_agents(find_agent, &s));
  if(!s.have_gpu) { std::fprintf(stderr, "FAIL:no-gpu-agent\n"); return 2; }
  char agent_name[64]{}; HSA_OK(hsa_agent_get_info(s.gpu, HSA_AGENT_INFO_NAME, agent_name));
  std::printf("STAGE:agent:%s\n", agent_name); std::fflush(stdout);
  HSA_OK(hsa_amd_agent_iterate_memory_pools(s.gpu, find_pool, &s));
  if(s.have_cpu) HSA_OK(hsa_amd_agent_iterate_memory_pools(s.cpu, find_pool, &s));
  if(!s.have_pool || s.pool_score < 1) { std::fprintf(stderr, "FAIL:no-fine-grained-global-pool\n"); return 2; }

  int fd = ::open(argv[2], O_RDONLY); if(fd < 0) { std::perror("open code object"); return 2; }
  hsa_code_object_reader_t reader{}; HSA_OK(hsa_code_object_reader_create_from_file(fd, &reader));
  hsa_executable_t exe{}; HSA_OK(hsa_executable_create_alt(HSA_PROFILE_FULL, HSA_DEFAULT_FLOAT_ROUNDING_MODE_DEFAULT, nullptr, &exe));
  HSA_OK(hsa_executable_load_agent_code_object(exe, s.gpu, reader, nullptr, nullptr));
  HSA_OK(hsa_executable_freeze(exe, nullptr));
  KernelInfo k; HSA_OK(hsa_executable_iterate_agent_symbols(exe, s.gpu, find_symbol, &k));
  if(!k.object) { std::fprintf(stderr, "FAIL:kernel-symbol-not-found\n"); return 2; }

  constexpr int N = 256;
  int* a = static_cast<int*>(alloc_shared(s, N * sizeof(int)));
  int* b = static_cast<int*>(alloc_shared(s, N * sizeof(int)));
  int* out = static_cast<int*>(alloc_shared(s, N * sizeof(int)));
  for(int i=0; i<N; ++i) { a[i] = i * 3 - 7; b[i] = i * 5 + 11; out[i] = 0x55555555; }
  struct alignas(16) Args { const int* a; const int* b; int* out; int n; };
  const size_t kernarg_alloc = k.kernarg > sizeof(Args) ? k.kernarg : sizeof(Args);
  void* kernarg = alloc_shared(s, kernarg_alloc);
  std::memset(kernarg, 0, kernarg_alloc);
  auto* args = static_cast<Args*>(kernarg);
  *args = Args{a, b, out, N};

  hsa_signal_t kernel_done{}, barrier_done{};
  HSA_OK(hsa_signal_create(1, 0, nullptr, &kernel_done));
  if(mixed) HSA_OK(hsa_signal_create(1, 0, nullptr, &barrier_done));
  hsa_queue_t* q = nullptr;
  HSA_OK(hsa_queue_create(s.gpu, 128, HSA_QUEUE_TYPE_SINGLE, nullptr, nullptr, UINT32_MAX, UINT32_MAX, &q));

  const uint64_t count = mixed ? 2 : 1;
  const uint64_t first = hsa_queue_add_write_index_scacq_screl(q, count);
  while(first + count - hsa_queue_load_read_index_scacquire(q) > q->size) { }
  static_assert(sizeof(hsa_kernel_dispatch_packet_t) == 64);
  static_assert(sizeof(hsa_barrier_and_packet_t) == 64);
  constexpr size_t packet_bytes = sizeof(hsa_kernel_dispatch_packet_t);
  auto* ring = static_cast<unsigned char*>(q->base_address);
  auto* kp = reinterpret_cast<hsa_kernel_dispatch_packet_t*>(ring + (first & (q->size - 1)) * packet_bytes);
  std::memset(kp, 0, sizeof(*kp));
  kp->setup = 1u << HSA_KERNEL_DISPATCH_PACKET_SETUP_DIMENSIONS;
  kp->workgroup_size_x = N; kp->workgroup_size_y = 1; kp->workgroup_size_z = 1;
  kp->grid_size_x = N; kp->grid_size_y = 1; kp->grid_size_z = 1;
  kp->private_segment_size = k.priv; kp->group_segment_size = k.group;
  kp->kernel_object = k.object; kp->kernarg_address = args; kp->completion_signal = kernel_done;
  publish_header(kp, header(HSA_PACKET_TYPE_KERNEL_DISPATCH, false));
  if(mixed) {
    auto* bp = reinterpret_cast<hsa_barrier_and_packet_t*>(ring + ((first + 1) & (q->size - 1)) * packet_bytes);
    std::memset(bp, 0, sizeof(*bp));
    bp->completion_signal = barrier_done;
    publish_header(bp, header(HSA_PACKET_TYPE_BARRIER_AND, false));
  }
  std::printf("STAGE:doorbell:first=%llu count=%llu writes=1\n", (unsigned long long)first, (unsigned long long)count); std::fflush(stdout);
  hsa_signal_store_screlease(q->doorbell_signal, first + count - 1);

  wait_zero(kernel_done, "kernel");
  if(mixed) wait_zero(barrier_done, "barrier");
  for(int i=0; i<N; ++i) {
    const int expected = a[i] + b[i];
    if(out[i] != expected) { std::fprintf(stderr, "FAIL:numeric:index=%d got=%d expected=%d\n", i, out[i], expected); return 4; }
  }
  std::printf("STAGE:numeric-pass elements=%d checksum=%lld\n", N, (long long)[&]{ long long x=0; for(int i=0;i<N;++i)x+=out[i]; return x; }()); std::fflush(stdout);
  std::printf("STAGE:ordinary-cleanup-begin\n"); std::fflush(stdout);
  HSA_OK(hsa_queue_destroy(q));
  HSA_OK(hsa_signal_destroy(kernel_done)); if(mixed) HSA_OK(hsa_signal_destroy(barrier_done));
  HSA_OK(hsa_amd_memory_pool_free(args)); HSA_OK(hsa_amd_memory_pool_free(out)); HSA_OK(hsa_amd_memory_pool_free(b)); HSA_OK(hsa_amd_memory_pool_free(a));
  HSA_OK(hsa_executable_destroy(exe)); HSA_OK(hsa_code_object_reader_destroy(reader)); ::close(fd);
  HSA_OK(hsa_shut_down());
  std::printf("STAGE:success\n"); std::fflush(stdout);
  return 0;
}
