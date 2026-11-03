/*
 * Test a workaround for EDT PDV 6.2.1 edt_set_event_func(), whose add-event ioctl
 * omits the event number (the driver registers event 0): after each call, send
 * ES_ADD_EVENT_FUNC again with the right event and mode, then close.
 *
 * usage: edt_event_fix CHANNEL EVENT CONTINUOUS REGISTRATIONS FIX
 * Exit status: 0 if close returned, 2 if it hung.
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "edtinc.h"

// The event ioctl codes are only in the driver header, which libpdv itself is built with
#include "driver/edt_ioctl.h"

enum { WATCHDOG_S = 10, SETTLE_US = 200000 };

static void on_event(void *data)
{
    (void)data;
    puts("event callback ran");
}

static void *watchdog(void *arg)
{
    (void)arg;
    sleep(WATCHDOG_S);
    printf("HUNG in pdv_close after %d s\n", WATCHDOG_S);
    fflush(stdout);
    _exit(2);
}

int main(int argc, char **argv)
{
    if (argc != 6) {
        fprintf(stderr, "usage: %s CHANNEL EVENT CONTINUOUS REGISTRATIONS FIX\n", argv[0]);
        return 1;
    }
    const unsigned int event = (unsigned int)atoi(argv[2]);
    const int continuous = atoi(argv[3]);
    const int registrations = atoi(argv[4]);
    const int fix = atoi(argv[5]);
    PdvDev pdv = pdv_open_channel("pdv", 0, atoi(argv[1]));
    if (pdv == NULL) {
        puts("open failed");
        return 1;
    }
    for (int i = 0; i < registrations; i++) {
        const int added = edt_set_event_func(pdv, (enum edt_kernel_event)event, on_event, NULL,
                                             continuous);
        int fixed = 0;
        if (fix) {
            unsigned int arg = ((unsigned int)continuous << EDT_EVENT_MODE_SHFT) | event;
            fixed = edt_ioctl(pdv, EDTS_ADD_EVENT_FUNC, &arg);
        }
        printf("registration %d: set_event_func=%d fix_add=%d\n", i + 1, added, fixed);
        usleep(SETTLE_US);
    }
    pthread_t guard;
    pthread_create(&guard, NULL, watchdog, NULL);
    pdv_close(pdv);
    puts("close returned");
    return 0;
}
