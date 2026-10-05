import {
  ChatProvider,
  ChatShell,
  type RetryConfig,
  type ShellHeaderConfig,
  type WelcomeHeaderConfig,
} from "@/components/chat";
import type { StarterPrompt } from "@/components/chat/types";
import { Sparkles } from "lucide-react"; // Example: import custom icon
import { useTranslation } from "react-i18next";

export default function Support() {
  const { t } = useTranslation();
  const BANKING_STARTER_PROMPTS: StarterPrompt[] = [
    {
      id: "card-trend",
      title: t("Review my accounts"),
      description: t("Account details and recorded balances"),
      icon: "💳",
      content: t("Show my bank accounts and their recorded balances"),
    },
    {
      id: "transactions-search",
      title: t("Review transactions"),
      description: t("Search your transaction history"),
      icon: "🛡️",
      content: t("Show my latest transactions"),
    },
    {
      id: "unauthorized-card-charge",
      title: t("Report an unauthorized card charge"),
      description: t("Get help with a card charge you do not recognize"),
      icon: "🛡️",
      content: t("I want to report a card charge I do not recognize"),
    },
  ];

  // Configure your chat server URL here
  const chatServerUrl = import.meta.env.VITE_RESPONSES_API_URL || "/responses";

  // Configure which HTTP status codes should allow retry
  // Default: [408, 429, 500, 502, 503, 504]
  const retryConfig: RetryConfig = {
    retryableStatusCodes: [408, 429, 500, 502, 503, 504],
  };

  // Configure header appearance and visibility
  // All properties are optional - omit to use defaults
  const headerConfig: ShellHeaderConfig = {
    showIcon: true, // Show/hide left icon badge
    // icon: Bot,                            // Custom icon (import from lucide-react)
    showTitle: true, // Show/hide title label
    titleLabel: t("Banking copilot"), // Custom title text
    showActiveThread: true, // Show/hide active thread name
    activeThreadFallback: t("Untitled thread"), // Text when no thread selected
    showNewThreadButton: true, // Show/hide new thread button
    showHistoryButton: true, // Show/hide history toggle button
    // customContent: <div>Custom Header</div> // Completely replace header content
  };

  // Configure welcome header (shown when no messages exist)
  // All properties are optional - omit to use defaults
  const welcomeHeaderConfig: WelcomeHeaderConfig = {
    icon: <Sparkles className="h-8 w-8 text-primary" />,
    title: t("Welcome to Banking Assistant"),
    subtitle: t("How can I help with your accounts or transactions?"),
  };

  return (
    <div className="relative flex h-full min-h-screen w-full items-center justify-center bg-slate-100 p-6">
      <div className="h-[720px] w-full max-w-5xl">
        <ChatProvider
          starterPrompts={BANKING_STARTER_PROMPTS}
          chatServerUrl={chatServerUrl}
          retryConfig={retryConfig}
          attachmentImageSize="lg"
          maxVisibleAttachments={3}
          welcomeHeaderConfig={welcomeHeaderConfig}
        >
          <ChatShell headerConfig={headerConfig} />
        </ChatProvider>
      </div>
    </div>
  );
}
