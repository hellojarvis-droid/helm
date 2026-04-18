import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { apiFetch } from "./api";

// Show notifications while the app is foregrounded. Users see the banner
// even during active use so they can't miss an approval landing mid-chat.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

/**
 * Request notification permission + register the Expo push token with the
 * backend. Call once after sign-in; no-op on simulators (Device.isDevice
 * is false) and when permission is denied.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  if (!Device.isDevice) return null;

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const req = await Notifications.requestPermissionsAsync();
    status = req.status;
  }
  if (status !== "granted") return null;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 120, 80, 120],
      lightColor: "#E85D1A",
    });
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    (Constants.easConfig as { projectId?: string } | undefined)?.projectId;
  try {
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await sendTokenToBackend(token);
    return token;
  } catch {
    return null;
  }
}

async function sendTokenToBackend(token: string | null): Promise<void> {
  try {
    await apiFetch("/auth/push_token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
  } catch {
    // Best-effort: if the token POST fails we try again next app launch.
  }
}

/**
 * Clear the stored token on sign-out so the server stops pushing to a
 * device that isn't ours anymore.
 */
export async function clearPushToken(): Promise<void> {
  await sendTokenToBackend(null);
}
