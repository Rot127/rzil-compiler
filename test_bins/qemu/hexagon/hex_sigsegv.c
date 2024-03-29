#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>

int err;

#include "hex_test.h"

bool segv_caught;

#define SHOULD_NOT_CHANGE_VAL        5
int32_t should_not_change = SHOULD_NOT_CHANGE_VAL;

#define BUF_SIZE        300
uint8_t buf[BUF_SIZE];
jmp_buf jmp_env;

static void sig_segv(int sig, siginfo_t *info, void *puc)
{
    check32(sig, SIGSEGV);
    segv_caught = true;
    longjmp(jmp_env, 1);
}

int main()
{
    struct sigaction act;

    /* SIGSEGV test */
    act.sa_sigaction = sig_segv;
    sigemptyset(&act.sa_mask);
    act.sa_flags = SA_SIGINFO;
    chk_error(sigaction(SIGSEGV, &act, NULL));
    if (setjmp(jmp_env) == 0) {
        asm volatile("r18 = ##should_not_change\n\t"
                     "r19 = #0\n\t"
                     "{\n\t"
                     "    memw(r18) = #7\n\t"
                     "    memw(r19) = #0\n\t"
                     "}\n\t"
                      : : : "r18", "r19", "memory");
    }

    act.sa_handler = SIG_DFL;
    sigemptyset(&act.sa_mask);
    act.sa_flags = 0;
    chk_error(sigaction(SIGSEGV, &act, NULL));

    check32(segv_caught, true);
    check32(should_not_change, SHOULD_NOT_CHANGE_VAL);

    puts(err ? "FAIL" : "PASS");
    return err ? EXIT_FAILURE : EXIT_SUCCESS;
}
