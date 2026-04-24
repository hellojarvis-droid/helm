import { Tabs } from "expo-router";
import { useEffect, useState } from "react";
import { AppState } from "react-native";
import { listApprovals } from "@/lib/api";
import { colors } from "@/lib/colors";

/**
 * Poll for pending approvals so the Approvals tab carries a native-style
 * numeric badge when the agent is waiting on the user. Refreshes every
 * 30s in foreground AND immediately when the app returns to foreground —
 * a backgrounded user who sees the push should find the badge already up
 * to date when they unlock.
 */
function usePendingApprovalCount(): number | undefined {
  const [count, setCount] = useState<number | undefined>(undefined);

  async function refresh() {
    try {
      const rows = await listApprovals("pending");
      setCount(rows.length || undefined);
    } catch {
      // Silent — badge stays at its last known value on error.
    }
  }

  useEffect(() => {
    void refresh();
    const interval = setInterval(refresh, 30_000);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void refresh();
    });
    return () => {
      clearInterval(interval);
      sub.remove();
    };
  }, []);

  return count;
}

// Tab order puts Chat first — Helm's product promise is Dispatch-style,
// one persistent thread with the CEO Agent as the primary surface.
// Today/Businesses/Approvals/Safety are secondary drill-downs.
export default function TabsLayout() {
  const pending = usePendingApprovalCount();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.ink3,
        headerStyle: { backgroundColor: colors.paper },
        headerTintColor: colors.ink,
        tabBarStyle: {
          backgroundColor: colors.paper,
          borderTopColor: colors.rule,
        },
      }}
    >
      <Tabs.Screen name="chat" options={{ title: "Atlas", tabBarLabel: "Atlas" }} />
      <Tabs.Screen name="today" options={{ title: "Today", tabBarLabel: "Today" }} />
      <Tabs.Screen
        name="approvals"
        options={{
          title: "Approvals",
          tabBarLabel: "Approvals",
          tabBarBadge: pending,
          tabBarBadgeStyle: {
            backgroundColor: colors.terracotta,
            color: colors.paper,
            fontSize: 11,
            fontWeight: "600",
          },
        }}
      />
      <Tabs.Screen name="businesses" options={{ title: "Businesses", tabBarLabel: "Businesses" }} />
      <Tabs.Screen name="safety" options={{ title: "Safety", tabBarLabel: "Safety" }} />
    </Tabs>
  );
}
