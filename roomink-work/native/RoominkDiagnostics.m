#import <React/RCTBridgeModule.h>
#import <CallKit/CallKit.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <sys/utsname.h>
#import <Security/Security.h>
#import <Network/Network.h>

static NSString * const RKQueueKey = @"roomink.diagnostics.v1";
static NSMutableDictionary *RKCallIds;
static BOOL RKUploading = NO;
static NSString *RKNetwork = @"unknown";
static nw_path_monitor_t RKMonitor;

static NSDictionary *RKCredentialQuery(void) {
  return @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
           (__bridge id)kSecAttrService: @"net.roomink.work.diagnostics",
           (__bridge id)kSecAttrAccount: @"device"};
}

static void RKAcknowledge(NSArray *identifiers) {
  @synchronized(NSUserDefaults.standardUserDefaults) {
    NSMutableArray *queue = [[NSUserDefaults.standardUserDefaults arrayForKey:RKQueueKey] mutableCopy] ?: [NSMutableArray new];
    NSIndexSet *indexes = [queue indexesOfObjectsPassingTest:^BOOL(NSDictionary *event, NSUInteger index, BOOL *stop) {
      return [identifiers containsObject:event[@"event_id"]];
    }];
    [queue removeObjectsAtIndexes:indexes];
    [NSUserDefaults.standardUserDefaults setObject:queue forKey:RKQueueKey];
  }
}

static void RKUpload(void) {
  @synchronized(NSUserDefaults.standardUserDefaults) {
    if (RKUploading) return;
    RKUploading = YES;
  }
  NSMutableDictionary *query = [RKCredentialQuery() mutableCopy];
  query[(__bridge id)kSecReturnData] = @YES;
  CFTypeRef value = NULL;
  OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &value);
  NSData *tokenData = CFBridgingRelease(value);
  NSString *token = status == errSecSuccess ? [[NSString alloc] initWithData:tokenData encoding:NSUTF8StringEncoding] : nil;
  NSURL *url = [NSURL URLWithString:[NSUserDefaults.standardUserDefaults stringForKey:@"roomink.diagnostics.endpoint"] ?: @""];
  NSArray *queue = [NSUserDefaults.standardUserDefaults arrayForKey:RKQueueKey] ?: @[];
  NSMutableArray *fresh = [NSMutableArray new];
  for (NSDictionary *event in queue) {
    NSISO8601DateFormatter *formatter = [NSISO8601DateFormatter new];
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    NSDate *date = [formatter dateFromString:event[@"observed_at"]] ?:
      [[NSISO8601DateFormatter new] dateFromString:event[@"observed_at"]];
    if (date && [date timeIntervalSinceNow] >= -7 * 86400) [fresh addObject:event];
    else RKAcknowledge(@[event[@"event_id"]]);
  }
  if (!token.length || ![url.scheme isEqualToString:@"https"] || !fresh.count) {
    @synchronized(NSUserDefaults.standardUserDefaults) { RKUploading = NO; }
    return;
  }
  NSArray *batch = [fresh subarrayWithRange:NSMakeRange(0, MIN(100, fresh.count))];
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
  request.HTTPMethod = @"POST";
  request.timeoutInterval = 10;
  [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
  [request setValue:[@"RoominkWork " stringByAppendingString:token] forHTTPHeaderField:@"Authorization"];
  request.HTTPBody = [NSJSONSerialization dataWithJSONObject:@{@"events": batch} options:0 error:nil];
  [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    if (!error && [(NSHTTPURLResponse *)response statusCode] == 200 && data) {
      id result = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
      if ([result isKindOfClass:NSDictionary.class] && [result[@"accepted"] isKindOfClass:NSArray.class]) {
        RKAcknowledge(result[@"accepted"]);
      }
    }
    @synchronized(NSUserDefaults.standardUserDefaults) { RKUploading = NO; }
  }] resume];
}

static void RKRecord(NSString *stage, NSString *sid, NSError *error) {
  // Only protocol identifiers and enumerated system state enter this queue.
  NSRegularExpression *pattern = [NSRegularExpression regularExpressionWithPattern:@"^CA[0-9a-fA-F]{32}$" options:0 error:nil];
  if (![sid isKindOfClass:NSString.class] || [pattern numberOfMatchesInString:sid options:0 range:NSMakeRange(0, sid.length)] != 1) sid = @"";
  struct utsname system;
  uname(&system);
  NSString *appState = @"unknown";
  if (NSThread.isMainThread) {
    switch (UIApplication.sharedApplication.applicationState) {
      case UIApplicationStateActive: appState = @"active"; break;
      case UIApplicationStateInactive: appState = @"inactive"; break;
      case UIApplicationStateBackground: appState = @"background"; break;
    }
  }
  NSMutableDictionary *snapshot = [@{
    @"os": UIDevice.currentDevice.systemVersion,
    @"model": [NSString stringWithUTF8String:system.machine],
    @"app_version": [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"unknown",
    @"build": [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown",
    @"revision": [[NSBundle mainBundle] objectForInfoDictionaryKey:@"RoominkDiagnosticRevision"] ?: @"unknown",
    @"network": RKNetwork,
    @"low_power": @(NSProcessInfo.processInfo.lowPowerModeEnabled),
    @"uptime_ms": @((long long)(NSProcessInfo.processInfo.systemUptime * 1000)),
    @"push_token_present": @([NSUserDefaults.standardUserDefaults boolForKey:@"roomink.diagnostics.push-token-present"]),
    @"app_state": appState
  } mutableCopy];
  if ([stage isEqualToString:@"registered"]) {
    [NSUserDefaults.standardUserDefaults setObject:[[NSISO8601DateFormatter new] stringFromDate:NSDate.date] forKey:@"roomink.diagnostics.last-registered"];
  }
  NSString *registeredAt = [NSUserDefaults.standardUserDefaults stringForKey:@"roomink.diagnostics.last-registered"];
  if (registeredAt) snapshot[@"last_registered_at"] = registeredAt;
  if (NSThread.isMainThread) snapshot[@"protected_data"] = @(UIApplication.sharedApplication.protectedDataAvailable);
  if (error) snapshot[@"error_code"] = @(error.code);
  NSISO8601DateFormatter *formatter = [NSISO8601DateFormatter new];
  formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
  NSDictionary *event = @{
    @"event_id": NSUUID.UUID.UUIDString, @"stage": stage, @"call_sid": sid,
    @"observed_at": [formatter stringFromDate:NSDate.date], @"snapshot": snapshot
  };
  @synchronized(NSUserDefaults.standardUserDefaults) {
    NSInteger sequence = [NSUserDefaults.standardUserDefaults integerForKey:@"roomink.diagnostics.sequence"] + 1;
    [NSUserDefaults.standardUserDefaults setInteger:sequence forKey:@"roomink.diagnostics.sequence"];
    snapshot[@"sequence"] = @(sequence);
    NSMutableArray *queue = [[NSUserDefaults.standardUserDefaults arrayForKey:RKQueueKey] mutableCopy] ?: [NSMutableArray new];
    [queue addObject:event];
    if (queue.count > 200) [queue removeObjectsInRange:NSMakeRange(0, queue.count - 200)];
    [NSUserDefaults.standardUserDefaults setObject:queue forKey:RKQueueKey];
  }
  RKUpload();
}

@interface CXProvider (RoominkDiagnostics)
- (void)rk_report:(NSUUID *)uuid update:(CXCallUpdate *)update completion:(void (^)(NSError *))completion;
@end
@implementation CXProvider (RoominkDiagnostics)
- (void)rk_report:(NSUUID *)uuid update:(CXCallUpdate *)update completion:(void (^)(NSError *))completion {
  NSString *sid;
  @synchronized(RKCallIds) { sid = RKCallIds[uuid.UUIDString]; }
  if (sid) RKRecord(@"callkit_requested", sid, nil);
  [self rk_report:uuid update:update completion:^(NSError *error) {
    if (sid) RKRecord(error ? @"callkit_failed" : @"callkit_reported", sid, error);
    if (completion) completion(error);
  }];
}
@end

@interface RoominkDiagnostics : NSObject <RCTBridgeModule>
@end
@interface RoominkDiagnosticsBootstrap : NSObject
@end
@implementation RoominkDiagnosticsBootstrap
+ (void)load {
  RKCallIds = [NSMutableDictionary new];
  RKMonitor = nw_path_monitor_create();
  nw_path_monitor_set_queue(RKMonitor, dispatch_get_main_queue());
  nw_path_monitor_set_update_handler(RKMonitor, ^(nw_path_t path) {
    if (nw_path_get_status(path) != nw_path_status_satisfied) RKNetwork = @"unavailable";
    else if (nw_path_uses_interface_type(path, nw_interface_type_wifi)) RKNetwork = @"wifi";
    else if (nw_path_uses_interface_type(path, nw_interface_type_cellular)) RKNetwork = @"cellular";
    else RKNetwork = @"other";
  });
  nw_path_monitor_start(RKMonitor);
  Class registryClass = NSClassFromString(@"TwilioVoicePushRegistry");
  SEL invalidateSelector = NSSelectorFromString(@"pushRegistry:didInvalidatePushTokenForType:");
  Method invalidateMethod = class_getInstanceMethod(registryClass, invalidateSelector);
  if (invalidateMethod) {
    IMP originalInvalidate = method_getImplementation(invalidateMethod);
    method_setImplementation(invalidateMethod, imp_implementationWithBlock(^(id instance, id registry, id type) {
      [NSUserDefaults.standardUserDefaults setBool:NO forKey:@"roomink.diagnostics.push-token-present"];
      RKRecord(@"registration_failed", @"", nil);
      ((void (*)(id, SEL, id, id))originalInvalidate)(instance, invalidateSelector, registry, type);
    }));
  }
  // Observe Twilio's native notification before React Native has started.
  [[NSNotificationCenter defaultCenter] addObserverForName:@"TwilioVoicePushRegistryNotification" object:nil queue:nil usingBlock:^(NSNotification *notification) {
    if ([notification.userInfo[@"type"] isEqual:@"deviceTokenUpdated"]) {
      [NSUserDefaults.standardUserDefaults setBool:YES forKey:@"roomink.diagnostics.push-token-present"];
    }
    for (id value in notification.userInfo.allValues) {
      if ([value isKindOfClass:NSDictionary.class] && value[@"twi_call_sid"]) {
        RKRecord(@"push_received", value[@"twi_call_sid"], nil);
      }
    }
  }];
  Method original = class_getInstanceMethod(CXProvider.class, @selector(reportNewIncomingCallWithUUID:update:completion:));
  Method replacement = class_getInstanceMethod(CXProvider.class, @selector(rk_report:update:completion:));
  method_exchangeImplementations(original, replacement);
  Class voiceClass = NSClassFromString(@"TwilioVoiceReactNative");
  SEL selector = NSSelectorFromString(@"reportNewIncomingCall:");
  Method method = class_getInstanceMethod(voiceClass, selector);
  if (method) {
    IMP implementation = method_getImplementation(method);
    IMP wrapped = imp_implementationWithBlock(^(id instance, id invite) {
      NSString *sid = [invite valueForKey:@"callSid"];
      NSUUID *uuid = [invite valueForKey:@"uuid"];
      if (sid && uuid) {
        @synchronized(RKCallIds) {
          if (RKCallIds.count >= 200) [RKCallIds removeAllObjects];
          RKCallIds[uuid.UUIDString] = sid;
        }
      }
      ((void (*)(id, SEL, id))implementation)(instance, selector, invite);
    });
    method_setImplementation(method, wrapped);
  }
  for (NSString *name in @[@"provider:performAnswerCallAction:", @"provider:performEndCallAction:"]) {
    SEL actionSelector = NSSelectorFromString(name);
    Method actionMethod = class_getInstanceMethod(voiceClass, actionSelector);
    if (!actionMethod) continue;
    IMP actionImplementation = method_getImplementation(actionMethod);
    NSString *stage = [name containsString:@"Answer"] ? @"accepted" : @"ended";
    IMP actionWrapped = imp_implementationWithBlock(^(id instance, CXProvider *provider, CXCallAction *action) {
      NSString *sid;
      @synchronized(RKCallIds) { sid = RKCallIds[action.callUUID.UUIDString]; }
      if (sid) RKRecord(stage, sid, nil);
      ((void (*)(id, SEL, id, id))actionImplementation)(instance, actionSelector, provider, action);
    });
    method_setImplementation(actionMethod, actionWrapped);
  }
  SEL connectSelector = NSSelectorFromString(@"callDidConnect:");
  Method connectMethod = class_getInstanceMethod(voiceClass, connectSelector);
  if (connectMethod) {
    IMP originalConnect = method_getImplementation(connectMethod);
    method_setImplementation(connectMethod, imp_implementationWithBlock(^(id instance, id call) {
      RKRecord(@"connected", [call valueForKey:@"sid"], nil);
      ((void (*)(id, SEL, id))originalConnect)(instance, connectSelector, call);
    }));
  }
  for (NSString *name in @[@"call:didDisconnectWithError:", @"call:didFailToConnectWithError:", @"call:isReconnectingWithError:"]) {
    SEL callSelector = NSSelectorFromString(name);
    Method callMethod = class_getInstanceMethod(voiceClass, callSelector);
    if (!callMethod) continue;
    IMP originalCall = method_getImplementation(callMethod);
    NSString *stage = [name containsString:@"Reconnecting"] ? @"reconnecting" :
      [name containsString:@"FailToConnect"] ? @"error" : @"ended";
    method_setImplementation(callMethod, imp_implementationWithBlock(^(id instance, id call, NSError *error) {
      RKRecord(stage, [call valueForKey:@"sid"], error);
      ((void (*)(id, SEL, id, id))originalCall)(instance, callSelector, call, error);
    }));
  }
}
@end

@implementation RoominkDiagnostics
RCT_EXPORT_MODULE();
+ (BOOL)requiresMainQueueSetup { return YES; }
RCT_REMAP_METHOD(read, readWithResolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) {
  @synchronized(NSUserDefaults.standardUserDefaults) {
    resolve([NSUserDefaults.standardUserDefaults arrayForKey:RKQueueKey] ?: @[]);
  }
}
RCT_EXPORT_METHOD(acknowledge:(NSArray *)identifiers) {
  RKAcknowledge(identifiers);
}
RCT_EXPORT_METHOD(configure:(NSString *)endpoint token:(NSString *)token) {
  NSURL *url = [NSURL URLWithString:endpoint];
  if (![url.scheme isEqualToString:@"https"] || ![url.path hasSuffix:@"/work/diagnostics/"] || !token.length) return;
  NSMutableDictionary *attributes = [RKCredentialQuery() mutableCopy];
  NSData *data = [token dataUsingEncoding:NSUTF8StringEncoding];
  OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)attributes,
    (__bridge CFDictionaryRef)@{(__bridge id)kSecValueData: data});
  if (status == errSecItemNotFound) {
    attributes[(__bridge id)kSecValueData] = data;
    attributes[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly;
    SecItemAdd((__bridge CFDictionaryRef)attributes, NULL);
  }
  [NSUserDefaults.standardUserDefaults setObject:endpoint forKey:@"roomink.diagnostics.endpoint"];
  RKUpload();
}
RCT_EXPORT_METHOD(clear) {
  SecItemDelete((__bridge CFDictionaryRef)RKCredentialQuery());
  [NSUserDefaults.standardUserDefaults removeObjectForKey:@"roomink.diagnostics.endpoint"];
  [NSUserDefaults.standardUserDefaults removeObjectForKey:RKQueueKey];
  [NSUserDefaults.standardUserDefaults removeObjectForKey:@"roomink.diagnostics.last-registered"];
}
RCT_EXPORT_METHOD(record:(NSString *)stage callSid:(NSString *)sid code:(NSNumber *)code) {
  NSSet *allowed = [NSSet setWithArray:@[@"registering", @"registered", @"registration_failed", @"invite", @"accepted", @"rejected", @"cancelled", @"connecting", @"connected", @"reconnecting", @"ended", @"error", @"app_state"]];
  if (![allowed containsObject:stage]) return;
  NSError *error = code ? [NSError errorWithDomain:@"RoominkVoice" code:code.integerValue userInfo:nil] : nil;
  RKRecord(stage, sid, error);
}
@end
