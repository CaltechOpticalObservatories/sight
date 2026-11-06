/*
 * Measure what the Camera Link serial line delivers with the camera off: read through
 * libpdv for a few seconds and report byte counts. Explains libnuvu's controller scan
 * behavior on a floating serial line.
 *
 * usage: serial_noise CHANNEL SECONDS
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#include "edtinc.h"

enum { CHUNK = 256, POLL_US = 1000 };

static long long now_ms(void)
{
    struct timespec now = {0};
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s CHANNEL SECONDS\n", argv[0]);
        return 1;
    }
    const int channel = atoi(argv[1]);
    const long long duration_ms = atol(argv[2]) * 1000;
    PdvDev pdv = pdv_open_channel("pdv", 0, channel);
    if (pdv == NULL) {
        printf("channel %d: open failed\n", channel);
        return 1;
    }
    long long total = 0;
    long long polls = 0;
    int first = -1;
    const long long start = now_ms();
    char buffer[CHUNK];
    while (now_ms() - start < duration_ms) {
        const int pending = pdv_serial_get_numbytes(pdv);
        polls++;
        if (pending > 0) {
            const int got = pdv_serial_read(pdv, buffer, pending < CHUNK ? pending : CHUNK);
            if (got > 0) {
                if (first < 0) {
                    first = (unsigned char)buffer[0];
                }
                total += got;
            }
        } else {
            usleep(POLL_US);
        }
    }
    printf("channel %d: %lld bytes in %lld ms (%lld polls), first byte %d\n", channel, total,
           duration_ms, polls, first);
    pdv_close(pdv);
    return 0;
}
