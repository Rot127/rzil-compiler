#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>

int err;

#include "hex_test.h"

#define insert(RES, X, WIDTH, OFFSET) \
    asm("r7 = %1\n\t" \
        "r7 = insert(r7, #" #WIDTH ", #" #OFFSET ")\n\t" \
        "%0 = r7\n\t" \
        : "=r"(RES) : "r"(X) : "r7")

static void test_insert(void)
{
    uint32_t res;

    insert(res, 0x12345678, 8, 1);
    check32(res, 0x123456f0);
    insert(res, 0x12345678, 0, 1);
    check32(res, 0x12345678);
    insert(res, 0x12345678, 20, 16);
    check32(res, 0x56785678);
}

static inline uint32_t insert_rp(uint32_t x, uint32_t width, uint32_t offset)
{
    uint64_t width_offset = (uint64_t)width << 32 | offset;
    uint32_t res;
    asm("r7 = %1\n\t"
        "r7 = insert(r7, %2)\n\t"
        "%0 = r7\n\t"
        : "=r"(res) : "r"(x), "r"(width_offset) : "r7");
    return res;

}

static void test_insert_rp(void)
{
    check32(insert_rp(0x12345678,   8,  1), 0x123456f0);
    check32(insert_rp(0x12345678,  63,  8), 0x34567878);
    check32(insert_rp(0x12345678, 127,  8), 0x34567878);
    check32(insert_rp(0x12345678,   8, 24), 0x78345678);
    check32(insert_rp(0x12345678,   8, 63), 0x12345678);
    check32(insert_rp(0x12345678,   8, 64), 0x00000000);
}

static inline uint32_t asr_r_svw_trun(uint64_t x, uint32_t y)
{
    uint32_t res;
    asm("r7 = %2\n\t"
        "r7 = vasrw(%1, r7)\n\t"
        "%0 = r7\n\t"
        : "=r"(res) : "r"(x), "r"(y) : "r7");
    return res;
}

static void test_asr_r_svw_trun(void)
{
    check32(asr_r_svw_trun(0x1111111122222222ULL, 5),
            0x88881111);
    check32(asr_r_svw_trun(0x1111111122222222ULL, 63),
            0x00000000);
    check32(asr_r_svw_trun(0x1111111122222222ULL, 64),
            0x00000000);
    check32(asr_r_svw_trun(0x1111111122222222ULL, 127),
            0x22224444);
    check32(asr_r_svw_trun(0x1111111122222222ULL, 128),
            0x11112222);
    check32(asr_r_svw_trun(0xffffffff22222222ULL, 128),
            0xffff2222);
}

static inline uint32_t swiz(uint32_t x)
{
    uint32_t res;
    asm("r7 = %1\n\t"
        "r7 = swiz(r7)\n\t"
        "%0 = r7\n\t"
        : "=r"(res) : "r"(x) : "r7");
    return res;
}

static void test_swiz(void)
{
    check32(swiz(0x11223344), 0x44332211);
}

int main()
{
    test_insert();
    test_insert_rp();
    test_asr_r_svw_trun();
    test_swiz();

    puts(err ? "FAIL" : "PASS");
    return err ? EXIT_FAILURE : EXIT_SUCCESS;
}
