import { formatDistanceToNow } from "date-fns";
import { Clock, FolderPlus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/common/utils";
import { useChat } from "./ResponsesChatProvider";
import { useTranslation } from "react-i18next";
import { enUS, es, pt } from "date-fns/locale";
import { SavedCaseConversations } from "./SavedCaseConversations";

export function HistoryView() {
  const { t, i18n } = useTranslation();
  const {
    threads,
    activeThreadId,
    selectThread,
    createThread,
    starterPrompts,
    getThreadItems,
  } = useChat();

  const renderThreads = () => (
    <div>
      <div className="grid gap-3 p-4 sm:grid-cols-2">
        {threads.map((thread) => {
          const threadItems = getThreadItems(thread.id);
          const latestMessage = threadItems.at(-1);
          const isActive = thread.id === activeThreadId;

          // Extract preview text from latest message
          let previewText = "";
          if (latestMessage?.type === "user_message") {
            const textContent = latestMessage.content.find(
              (c) => c.type === "input_text",
            );
            previewText =
              textContent && textContent.type === "input_text"
                ? textContent.text
                : "";
          } else if (latestMessage?.type === "assistant_message") {
            previewText = latestMessage.content.map((c) => c.text).join("");
          }

          return (
            <Card
              key={thread.id}
              className={cn(
                "flex cursor-pointer flex-col gap-3 border border-border/70 px-4 py-3 transition",
                isActive
                  ? "border-primary bg-primary/5"
                  : "hover:border-primary/60",
              )}
              onClick={() => selectThread(thread.id)}
            >
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {formatDistanceToNow(new Date(thread.created_at), {
                    addSuffix: true,
                    locale:
                      i18n.language === "es"
                        ? es
                        : i18n.language === "pt"
                          ? pt
                          : enUS,
                  })}
                </span>
                <Badge
                  variant={
                    thread.status.type === "active" ? "secondary" : "outline"
                  }
                >
                  {t(`Conversation status ${thread.status.type}`)}
                </Badge>
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {thread.title || t("Untitled thread")}
                </p>
              </div>
              {previewText && (
                <p
                  className="text-xs text-muted-foreground"
                  title={previewText}
                >
                  {previewText.slice(0, 120)}
                  {previewText.length > 120 ? "…" : ""}
                </p>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );

  const renderStarterPrompts = () => (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-6 text-center">
      <div className="space-y-1">
        <p className="text-lg font-semibold text-foreground">
          {t("Start a new banking conversation")}
        </p>
        <p className="text-sm text-muted-foreground">
          {t("Choose a template prompt or craft your own request.")}
        </p>
      </div>
      <div className="grid w-full max-w-2xl gap-3 sm:grid-cols-2">
        {starterPrompts.map((prompt) => (
          <Button
            key={prompt.id}
            variant="outline"
            className="flex h-auto flex-col items-start gap-1 rounded-2xl border-border/70 px-4 py-3 text-left"
            onClick={() =>
              createThread(prompt.content, { title: prompt.title })
            }
          >
            <span className="text-sm font-semibold text-foreground">
              {prompt.icon ? `${prompt.icon} ` : ""}
              {prompt.title}
            </span>
            {prompt.description && (
              <span className="text-xs text-muted-foreground">
                {prompt.description}
              </span>
            )}
          </Button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-muted/20">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {t("Thread history")}
          </p>
          <p className="text-sm font-medium text-foreground">
            {t("Pick a conversation or spin up a new one.")}
          </p>
        </div>
        <Button size="sm" className="gap-1" onClick={() => createThread()}>
          <FolderPlus className="h-4 w-4" /> {t("New thread")}
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <section aria-label={t("Session chats")}>
          <div className="space-y-1 px-4 pt-4">
            <h2 className="text-sm font-semibold">{t("Session chats")}</h2>
            <p className="text-xs text-muted-foreground">{t("Session chats description")}</p>
          </div>
          {threads.length ? (
            <>
              {renderThreads()}
              <Separator className="mx-4" />
              <div className="flex flex-col gap-2 px-4 py-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Clock className="h-3.5 w-3.5" />
                  <span>{t("Threads are sorted by most recent activity.")}</span>
                </div>
              </div>
            </>
          ) : (
            renderStarterPrompts()
          )}
        </section>
        <Separator />
        <SavedCaseConversations />
      </ScrollArea>
    </div>
  );
}
