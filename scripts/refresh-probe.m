// Temporary Settings diagnostic; reads display policy without changing frame-rate requests.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <math.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

static NSString *
readValue(id object, NSString *key)
{
    if (!object) return @"unavailable";
    @try {
        return [[object valueForKey:key] description] ?: @"nil";
    } @catch (NSException *exception) {
        return [NSString stringWithFormat:@"unavailable (%@)", exception.name];
    }
}

#ifdef ISHTAR_REFRESH_PROBE_CHECK
@interface ProbeFixture : NSObject
@property NSInteger maximumFramesPerSecond;
@property double minimumFrameDuration;
@property (copy) NSString *name;
+ (id)mainDisplay;
@end
@implementation ProbeFixture
+ (id)mainDisplay { return @"display"; }
@end
int main(void)
{
    @autoreleasepool {
        ProbeFixture *fixture = [ProbeFixture new];
        fixture.maximumFramesPerSecond = 120;
        fixture.minimumFrameDuration = 1.0 / 120;
        fixture.name = @"display";
        NSCAssert([readValue(fixture, @"maximumFramesPerSecond") isEqual:@"120"], @"integer boxing");
        NSCAssert(fabs(readValue(fixture, @"minimumFrameDuration").doubleValue - 1.0 / 120) < 1e-9, @"double boxing");
        NSCAssert([readValue(fixture, @"name") isEqual:@"display"], @"object return");
        NSCAssert([[ProbeFixture valueForKey:@"mainDisplay"] isEqual:@"display"], @"class getter");
        NSCAssert([readValue(fixture, @"missing") hasPrefix:@"unavailable"], @"unsupported key");
        NSCAssert([readValue(nil, @"name") isEqual:@"unavailable"], @"missing display");
        puts("refresh probe: scalar, object, unsupported-key and nil checks passed");
    }
}
#else
static void
emit(NSString *line)
{
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return;
    struct sockaddr_in address = { .sin_len = sizeof(address), .sin_family = AF_INET, .sin_port = htons(5140) };
    inet_pton(AF_INET, "192.168.7.1", &address.sin_addr);
    NSData *data = [[@"ISHTAR REFRESH PROBE: " stringByAppendingString:line] dataUsingEncoding:NSUTF8StringEncoding];
    (void)sendto(fd, data.bytes, data.length, 0, (struct sockaddr *)&address, sizeof(address));
    close(fd);
}

__attribute__((constructor)) static void
refreshProbe(void)
{
    emit(@"library loaded\n");
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 7 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        @autoreleasepool {
            emit(@"main-queue callback started\n");
            NSMutableString *log = [NSMutableString stringWithFormat:@"%@ pid=%d bundle=%@ optIn=%@\n",
                NSDate.date, getpid(), NSBundle.mainBundle.bundleIdentifier,
                NSBundle.mainBundle.infoDictionary[@"CADisableMinimumFrameDurationOnPhone"]];
            Class screenClass = NSClassFromString(@"UIScreen");
            Class displayClass = NSClassFromString(@"CADisplay");
            emit(log);
            id screen = [screenClass respondsToSelector:NSSelectorFromString(@"mainScreen")] ?
                [screenClass valueForKey:@"mainScreen"] : nil;
            id display = [displayClass respondsToSelector:NSSelectorFromString(@"mainDisplay")] ?
                [displayClass valueForKey:@"mainDisplay"] : nil;
            for (NSString *key in @[@"maximumFramesPerSecond", @"bounds", @"nativeBounds"]) {
                NSString *line = [NSString stringWithFormat:@"UIScreen.%@ = %@\n", key, readValue(screen, key)];
                [log appendString:line];
                emit(line);
            }
            for (NSString *key in @[@"refreshRate", @"hardwareRefreshRate", @"minimumFrameDuration",
                    @"supportsVariableFrameDuration", @"currentMode", @"availableModes",
                    @"highestLocalPreferredFrameRateRequest"]) {
                NSString *line = [NSString stringWithFormat:@"CADisplay.%@ = %@\n", key, readValue(display, key)];
                [log appendString:line];
                emit(line);
            }
            void *mg = dlopen("/usr/lib/libMobileGestalt.dylib", RTLD_NOW | RTLD_LOCAL);
            CFTypeRef (*copyAnswer)(CFStringRef) = mg ? dlsym(mg, "MGCopyAnswer") : NULL;
            if (copyAnswer) {
                CFTypeRef answer = copyAnswer(CFSTR("SupportsPerseus"));
                [log appendFormat:@"SupportsPerseus = %@\n", answer ? (__bridge id)answer : @"unavailable"];
                if (answer) CFRelease(answer);
            } else {
                [log appendString:@"SupportsPerseus = unavailable (MGCopyAnswer)\n"];
            }
            if (mg) dlclose(mg);
            emit(log);
            NSError *error = nil;
            if (![log writeToFile:@"/private/var/tmp/ishtar-refresh-probe.log" atomically:YES
                    encoding:NSUTF8StringEncoding error:&error]) {
                NSLog(@"ishtar refresh probe: %@", error);
            }
        }
    });
}
#endif
