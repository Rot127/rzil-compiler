#include <stdio.h>
#include <signal.h>
#include <time.h>

void sig_user(int sig, siginfo_t *info, void *puc)
{
    asm("r7 = #0\n\t"
        "p0 = r7\n\t"
        "p1 = r7\n\t"
        "p2 = r7\n\t"
        "p3 = r7\n\t"
        : : : "r7", "p0", "p1", "p2", "p3");
}

int main()
{
    int err = 0;
    unsigned int i = 100000;
    struct sigaction act;
    struct itimerspec it;
    timer_t tid;
    struct sigevent sev;

    act.sa_sigaction = sig_user;
    sigemptyset(&act.sa_mask);
    act.sa_flags = SA_SIGINFO;
    sigaction(SIGUSR1, &act, NULL);
    sev.sigev_notify = SIGEV_SIGNAL;
    sev.sigev_signo = SIGUSR1;
    sev.sigev_value.sival_ptr = &tid;
    timer_create(CLOCK_REALTIME, &sev, &tid);
    it.it_interval.tv_sec = 0;
    it.it_interval.tv_nsec = 100000;
    it.it_value.tv_sec = 0;
    it.it_value.tv_nsec = 100000;
    timer_settime(tid, 0, &it, NULL);

    asm("loop0(1f, %1)\n\t"
        "1: r8 = #0xff\n\t"
        "   p0 = r8\n\t"
        "   p1 = r8\n\t"
        "   p2 = r8\n\t"
        "   p3 = r8\n\t"
        "   jump 3f\n\t"
        "2: memb(%0) = #1\n\t"
        "   jump 4f\n\t"
        "3:\n\t"
        "   r8 = p0\n\t"
        "   p0 = cmp.eq(r8, #0xff)\n\t"
        "   if (!p0) jump 2b\n\t"
        "   r8 = p1\n\t"
        "   p0 = cmp.eq(r8, #0xff)\n\t"
        "   if (!p0) jump 2b\n\t"
        "   r8 = p2\n\t"
        "   p0 = cmp.eq(r8, #0xff)\n\t"
        "   if (!p0) jump 2b\n\t"
        "   r8 = p3\n\t"
        "   p0 = cmp.eq(r8, #0xff)\n\t"
        "   if (!p0) jump 2b\n\t"
        "4: {}: endloop0\n\t"
        :
        : "r"(&err), "r"(i)
        : "memory", "r8", "p0", "p1", "p2", "p3");

    puts(err ? "FAIL" : "PASS");
    return err;
}
