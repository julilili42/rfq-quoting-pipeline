import type { MailAttachment, MailSnapshot } from "../types";

declare const Office: any;

export type SelectedMailSummary = {
  itemId: string;
  subject: string;
  sender?: string;
  conversationId?: string;
  internetMessageId?: string;
  hasAttachment: boolean;
  collapsedCount: number;
};

function formatFrom(item: any): string {
  const from = item.from;
  if (!from) return "(unknown)";
  const displayName = from.displayName || "";
  const emailAddress = from.emailAddress || "";
  if (displayName && emailAddress) {
    return `${displayName} <${emailAddress}>`;
  }
  return displayName || emailAddress || "(unknown)";
}

async function getAttachmentsWithContent(
  item: any,
): Promise<MailAttachment[]> {
  const attachments = item.attachments || [];
  const results: MailAttachment[] = [];
  for (const att of attachments) {
    const content = await new Promise<string>((resolve, reject) => {
      item.getAttachmentContentAsync(att.id, (result: any) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve(result.value.content);
        } else {
          reject(result.error?.message || "attachment fetch failed");
        }
      });
    });

    results.push({
      name: att.name || "(unnamed)",
      contentType: att.contentType || "application/octet-stream",
      size: att.size || 0,
      id: att.id || "",
      contentBase64: content,
    });
  }
  return results;
}

function getBodyText(item: any): Promise<string> {
  return new Promise((resolve, reject) => {
    item.body.getAsync(Office.CoercionType.Text, (result: any) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) {
        resolve(result.value || "(empty body)");
      } else {
        reject(result.error?.message || "unknown error");
      }
    });
  });
}

async function readMailSnapshotFromItem(item: any): Promise<MailSnapshot> {
  return {
    subject: item.subject || "(no subject)",
    from: formatFrom(item),
    body: await getBodyText(item),
    attachments: await getAttachmentsWithContent(item),
  };
}

export async function readMailSnapshot(): Promise<MailSnapshot> {
  const item = Office.context.mailbox.item;
  return readMailSnapshotFromItem(item);
}

export function getSelectedMailItems(): Promise<SelectedMailSummary[]> {
  const mailbox = Office.context?.mailbox;
  if (!mailbox?.getSelectedItemsAsync) {
    return Promise.resolve([]);
  }

  return new Promise((resolve) => {
    try {
      mailbox.getSelectedItemsAsync((result: any) => {
        if (result.status !== Office.AsyncResultStatus.Succeeded) {
          resolve([]);
          return;
        }
        const items = Array.isArray(result.value) ? result.value : [];
        resolve(collapseSelectedItems(items));
      });
    } catch {
      resolve([]);
    }
  });
}

function selectedItemKey(item: SelectedMailSummary): string {
  return item.conversationId || item.itemId;
}

function isBetterRepresentative(
  candidate: SelectedMailSummary,
  current: SelectedMailSummary,
): boolean {
  if (candidate.hasAttachment !== current.hasAttachment) {
    return candidate.hasAttachment;
  }
  return false;
}

export function collapseSelectedItems(items: any[]): SelectedMailSummary[] {
  const bySelectionKey = new Map<string, SelectedMailSummary>();

  for (const item of items) {
    if (!item?.itemId) continue;

    const summary: SelectedMailSummary = {
      itemId: String(item.itemId),
      subject: item.subject || "(no subject)",
      sender: item.from ? formatFrom(item) : undefined,
      conversationId: item.conversationId
        ? String(item.conversationId)
        : undefined,
      internetMessageId: item.internetMessageId
        ? String(item.internetMessageId)
        : undefined,
      hasAttachment: Boolean(item.hasAttachment),
      collapsedCount: 1,
    };

    const key = selectedItemKey(summary);
    const current = bySelectionKey.get(key);
    if (!current) {
      bySelectionKey.set(key, summary);
      continue;
    }

    current.collapsedCount += 1;
    if (isBetterRepresentative(summary, current)) {
      bySelectionKey.set(key, {
        ...summary,
        collapsedCount: current.collapsedCount,
      });
    }
  }

  return Array.from(bySelectionKey.values());
}

export async function readSelectedMailSnapshot(
  itemId: string,
): Promise<MailSnapshot> {
  const mailbox = Office.context?.mailbox;
  if (!mailbox?.loadItemByIdAsync) {
    throw new Error("Outlook unterstützt das Laden ausgewählter Mails nicht.");
  }

  const loadedItem = await new Promise<any>((resolve, reject) => {
    mailbox.loadItemByIdAsync(itemId, (result: any) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) {
        resolve(result.value);
      } else {
        reject(result.error?.message || "selected mail load failed");
      }
    });
  });

  try {
    return await readMailSnapshotFromItem(loadedItem);
  } finally {
    await new Promise<void>((resolve) => {
      if (!loadedItem?.unloadAsync) {
        resolve();
        return;
      }
      loadedItem.unloadAsync(() => resolve());
    });
  }
}

export async function readSelectedMailSummaryHeader(
  item: SelectedMailSummary,
): Promise<SelectedMailSummary> {
  if (item.sender) return item;

  const mailbox = Office.context?.mailbox;
  if (!mailbox?.loadItemByIdAsync) return item;

  let loadedItem: any | null = null;
  try {
    loadedItem = await new Promise<any>((resolve, reject) => {
      mailbox.loadItemByIdAsync(item.itemId, (result: any) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve(result.value);
        } else {
          reject(result.error?.message || "selected mail load failed");
        }
      });
    });

    return {
      ...item,
      subject: item.subject,
      sender: formatFrom(loadedItem),
      hasAttachment: Boolean(loadedItem.attachments?.length) || item.hasAttachment,
    };
  } catch {
    return item;
  } finally {
    if (loadedItem?.unloadAsync) {
      await new Promise<void>((resolve) => {
        loadedItem.unloadAsync(() => resolve());
      });
    }
  }
}
