import { AuthGuard } from "@/components/auth-guard";
import { Sidebar } from "@/components/sidebar";
import { ChatWidget } from "@/components/chat/ChatWidget";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-8">{children}</main>
        <ChatWidget />
      </div>
    </AuthGuard>
  );
}
