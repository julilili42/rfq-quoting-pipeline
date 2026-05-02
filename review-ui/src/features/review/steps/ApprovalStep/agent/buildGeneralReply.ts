import type { Quotation } from "@/shared/schemas/quotation";
import { formatEur } from "@/shared/lib/format";

import type { AgentLang } from "./i18n";
import { t } from "./i18n";

/**
 * Generic agent reply for messages that aren't recognised commands.
 *
 * Mirrors `quoting/ui/review_agent.build_general_agent_reply`. The
 * intent is to answer obvious questions about the current quotation
 * ("what is the total?", "any warnings?") without leaving the user
 * in silence when a command parses as plain prose.
 */
export function buildGeneralReply(
  message: string,
  quotation: Quotation | null,
  lang: AgentLang,
): string {
  const text = message.toLowerCase();

  if (quotation && /(total|sum|gesamt)/.test(text)) {
    return t(lang, "reply_total", { total: formatEur(quotation.gesamtsumme) });
  }

  if (/(warning|warn|risk|risiko)/.test(text)) {
    if (!quotation || quotation.warnungen.length === 0) {
      return t(lang, "reply_no_warnings");
    }
    return [
      t(lang, "reply_warnings_header"),
      ...quotation.warnungen.map((w) => `- ${w}`),
    ].join("\n");
  }

  return t(lang, "reply_help");
}
