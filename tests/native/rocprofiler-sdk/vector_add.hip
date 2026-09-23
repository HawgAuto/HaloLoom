#include <hip/hip_runtime.h>

extern "C" __global__ void fixture_vector_add(const int* a, const int* b, int* out, int n)
{
    const int i = (int) threadIdx.x;
    if(i < n) out[i] = a[i] + b[i];
}
