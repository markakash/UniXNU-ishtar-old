// Temporary Settings test: default display link, then an explicit 120 fps request, with no drawing.
#import <Foundation/Foundation.h>
#include <math.h>

static double
callbackRate(unsigned samples, double first, double last)
{
    return samples > 1 && last > first ? (samples - 1) / (last - first) : 0;
}

#ifdef ISHTAR_REFRESH_PROBE_CHECK
int main(void)
{
    NSCAssert(fabs(callbackRate(361, 10, 13) - 120) < 1e-9, @"120 fps");
    NSCAssert(fabs(callbackRate(181, 10, 13) - 60) < 1e-9, @"60 fps");
    NSCAssert(callbackRate(0, 0, 0) == 0 && callbackRate(1, 10, 10) == 0, @"no interval");
    puts("display-link probe: rate and missing-interval checks passed");
}
#else
#import <QuartzCore/QuartzCore.h>
#import "refresh-probe.m"

@interface IshtarRefreshLinkProbe : NSObject
@property (strong) CADisplayLink *link;
@property unsigned phase, samples;
@property double first, last, maxGap;
- (void)start;
@end

@implementation IshtarRefreshLinkProbe
- (void)start
{
    self.samples = 0;
    self.first = self.last = self.maxGap = 0;
    self.link = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
    if (self.phase == 1) self.link.preferredFrameRateRange = CAFrameRateRangeMake(120, 120, 120);
    CAFrameRateRange range = self.link.preferredFrameRateRange;
    emit([NSString stringWithFormat:@"LINK begin phase=%u requested=%g/%g/%g\n",
        self.phase, range.minimum, range.maximum, range.preferred]);
    [self.link addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
}
- (void)tick:(CADisplayLink *)link
{
    double now = CACurrentMediaTime();
    if (!self.samples) self.first = now;
    else self.maxGap = fmax(self.maxGap, now - self.last);
    self.last = now;
    self.samples++;
    if (now - self.first < 3) return;
    emit([NSString stringWithFormat:@"LINK end phase=%u callbacks=%u seconds=%.6f fps=%.3f maxGap_ms=%.3f duration=%.9f\n",
        self.phase, self.samples, now - self.first, callbackRate(self.samples, self.first, self.last),
        self.maxGap * 1000, link.duration]);
    [self.link invalidate];
    self.link = nil;
    if (self.phase++ == 0) [self start];
    else emit(@"LINK done; both links invalidated\n");
}
@end

__attribute__((constructor)) static void
refreshLinkProbe(void)
{
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        IshtarRefreshLinkProbe *probe = [IshtarRefreshLinkProbe new];
        [probe start];
        // Bound the test even if callbacks stop or the app enters the background.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 15 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            [probe.link invalidate];
            probe.link = nil;
        });
    });
}
#endif
