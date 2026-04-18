import { Tabs } from "expo-router";
import { colors } from "@/lib/colors";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.iron,
        headerStyle: { backgroundColor: colors.paper },
        headerTintColor: colors.ink,
        tabBarStyle: { backgroundColor: colors.paper, borderTopColor: "rgba(107,107,107,0.2)" },
      }}
    >
      <Tabs.Screen name="chat" options={{ title: "Chat", tabBarLabel: "Chat" }} />
      <Tabs.Screen name="businesses" options={{ title: "Businesses", tabBarLabel: "Businesses" }} />
      <Tabs.Screen name="approvals" options={{ title: "Approvals", tabBarLabel: "Approvals" }} />
    </Tabs>
  );
}
