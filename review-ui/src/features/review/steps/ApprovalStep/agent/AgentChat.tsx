import { Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { upsertOverride } from "@/features/review/steps/PositionsStep/upsertOverride";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/cn";
import type { Anfrage } from "@/shared/schemas/anfrage";
import type { ManualOverride, Quotation } from "@/shared/schemas/quotation";

import { useSaveAndRegenerate } from "../../../hooks/useReviewMutations";
import { buildGeneralReply } from "./buildGeneralReply";
import { detectAgentLanguage } from "./detectLanguage";
import { t, type AgentLang } from "./i18n";
import { parseEditInstruction } from "./parseInstruction";

interface AgentChatProps {
  reviewId: string;
  anfrage: Anfrage;
  quotation: Quotation | null;
  overrides: ManualOverride[];
}

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  /** Stable id for keyed rendering — Date.now() is good enough. */
  id: string;
}

/**
 * Natural-language commercial-edit chat.
 *
 * Mirrors the Streamlit `agent_chat` panel: user types an instruction,
 * we parse it client-side, push the resulting override into the
 * quotation flow, and let the existing regenerate mutation handle the
 * PDF rebuild. No new API surface required.
 *
 * Layout follows the Streamlit version: input at the top, messages
 * below — reversed from a typical chat because here the input is the
 * primary interaction and the history is reference material.
 */
export function AgentChat({ reviewId, anfrage, quotation, overrides }: AgentChatProps) {
  const lang: AgentLang = useMemo(
    () =>
      detectAgentLanguage(
        // sample the customer fields and a few source quotes — same
        // heuristic as the Python side
        [
          anfrage.kunde_firma ?? "",
          anfrage.kunde_ansprechpartner ?? "",
          anfrage.belegnummer ?? "",
          ...anfrage.positionen.slice(0, 3).map((p) => p.source_quote ?? ""),
        ].join(" "),
      ),
    [anfrage],
  );

  const knownArticles = useMemo(
    () =>
      anfrage.positionen
        .map((p) => p.artikelnummer)
        .filter((s): s is string => Boolean(s && s.trim())),
    [anfrage.positionen],
  );

  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll the message list as new entries appear.
  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length]);

  const saveAndRegenerate = useSaveAndRegenerate(reviewId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const message = draft.trim();
    if (!message) return;
    setDraft("");

    const newMessages: AgentMessage[] = [
      ...messages,
      { role: "user", content: message, id: `u-${Date.now()}` },
    ];

    const { override, feedback } = parseEditInstruction(
      message,
      knownArticles,
      lang,
    );

    if (override) {
      const nextOverrides = upsertOverride(overrides, override);
      saveAndRegenerate.mutate(
        { overrides: nextOverrides },
        {
          onSuccess: () => {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: feedback,
                id: `a-${Date.now()}`,
              },
            ]);
          },
          onError: (err) => {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: t(lang, "rebuild_failed", {
                  error: err instanceof Error ? err.message : String(err),
                }),
                id: `a-${Date.now()}`,
              },
            ]);
          },
        },
      );
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content: t(lang, "rebuilding"),
          id: `a-${Date.now()}-pending`,
        },
      ]);
      return;
    }

    if (feedback) {
      setMessages([
        ...newMessages,
        { role: "assistant", content: feedback, id: `a-${Date.now()}` },
      ]);
      return;
    }

    setMessages([
      ...newMessages,
      {
        role: "assistant",
        content: buildGeneralReply(message, quotation, lang),
        id: `a-${Date.now()}`,
      },
    ]);
  };

  return (
    <section
      className="rounded-lg border border-border bg-surface p-5 shadow-card"
      aria-label="Agent-Chat"
    >
      <div className="section-label mb-3">
        Agent-Chat · Anpassungen in Klartext
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t(lang, "chat_placeholder")}
          aria-label="Anpassung schreiben"
          disabled={saveAndRegenerate.isPending}
        />
        <Button type="submit" variant="primary" disabled={!draft.trim()}>
          <Send className="h-4 w-4" aria-hidden="true" />
          Senden
        </Button>
      </form>

      {messages.length === 0 ? (
        <p className="mt-4 rounded-md border border-info/30 bg-info-soft px-3 py-2 text-xs text-info">
          {t(lang, "intro")}
        </p>
      ) : (
        <div
          ref={listRef}
          className="mt-4 max-h-72 space-y-2 overflow-y-auto pr-1"
          aria-live="polite"
        >
          {messages.map((m) => (
            <ChatBubble key={m.id} role={m.role} content={m.content} />
          ))}
        </div>
      )}
    </section>
  );
}

function ChatBubble({
  role,
  content,
}: {
  role: AgentMessage["role"];
  content: string;
}) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
          isUser
            ? "bg-foreground text-background"
            : "border border-border bg-muted text-foreground",
        )}
      >
        {content}
      </div>
    </div>
  );
}
