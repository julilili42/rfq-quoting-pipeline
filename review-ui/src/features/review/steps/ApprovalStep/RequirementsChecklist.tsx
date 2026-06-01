import {
  Award,
  CalendarClock,
  ChevronRight,
  FileSearch,
  Info,
  Package,
  Paperclip,
  Truck,
  X,
  type LucideIcon,
} from "lucide-react";
import { useMemo, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";

import type { OutgoingMailAttachment } from "@/shared/api/reviews";
import { Button, buttonVariants } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { cn } from "@/shared/lib/cn";
import type {
  Anforderung,
  AnforderungKategorie,
} from "@/shared/schemas/anfrage";

import {
  useAcknowledgeRequirements,
  useDeleteMailAttachment,
  useUploadMailAttachment,
} from "../../hooks/useReviewMutations";

interface RequirementsChecklistProps {
  anforderungen: Anforderung[];
  acknowledgedIndices: number[];
  mailAttachments: OutgoingMailAttachment[];
}

interface RequirementGroup {
  id: string;
  title: string;
  category: AnforderungKategorie;
  indices: number[];
  sourceQuotes: string[];
  posNrs: number[];
}

interface RequirementGroupDescriptor {
  id: string;
  title: string;
  category: AnforderungKategorie;
}

interface RequirementRule extends RequirementGroupDescriptor {
  matches: (item: Anforderung, searchText: string) => boolean;
}

const KATEGORIE_META: Record<
  AnforderungKategorie,
  { label: string; icon: LucideIcon }
> = {
  zeichnung: { label: "Zeichnung", icon: FileSearch },
  zertifikat: { label: "Zertifikat", icon: Award },
  verpackung: { label: "Verpackung", icon: Package },
  logistik: { label: "Logistik", icon: Truck },
  termin: { label: "Termin", icon: CalendarClock },
  sonstige: { label: "Sonstige", icon: Info },
};

const REQUIREMENT_RULES: RequirementRule[] = [
  {
    id: "commercial-terms",
    title: "Aktuelle Preise und Lieferzeit im Angebot angeben",
    category: "sonstige",
    matches: (_item, searchText) =>
      searchText.includes("preis") && searchText.includes("lieferzeit"),
  },
  {
    id: "packaging-weight",
    title: "Verpackungsart sowie Brutto-/Nettogewicht angeben",
    category: "verpackung",
    matches: (item, searchText) =>
      item.kategorie === "verpackung" &&
      (searchText.includes("verpack") ||
        searchText.includes("gewicht") ||
        searchText.includes("brutto") ||
        searchText.includes("netto")),
  },
  {
    id: "drawings",
    title: "Aktuell gültige Zeichnungen beilegen",
    category: "zeichnung",
    matches: (item, searchText) =>
      item.kategorie === "zeichnung" || searchText.includes("zeichnung"),
  },
  {
    id: "certificates",
    title: "Zertifikate und Prüfzeugnisse beilegen",
    category: "zertifikat",
    matches: (item, searchText) =>
      item.kategorie === "zertifikat" ||
      searchText.includes("zertifikat") ||
      searchText.includes("prufzeugnis"),
  },
  {
    id: "logistics",
    title: "Logistikvorgaben berücksichtigen",
    category: "logistik",
    matches: (item) => item.kategorie === "logistik",
  },
  {
    id: "deadline",
    title: "Terminvorgaben berücksichtigen",
    category: "termin",
    matches: (item) => item.kategorie === "termin",
  },
];

const ATTACHMENT_SOLVABLE_CATEGORIES = new Set<AnforderungKategorie>([
  "zeichnung",
  "zertifikat",
]);

export function RequirementsChecklist({
  anforderungen,
  acknowledgedIndices,
  mailAttachments,
}: RequirementsChecklistProps) {
  const { reviewId } = useParams<{ reviewId: string }>();
  const acknowledge = useAcknowledgeRequirements(reviewId);
  const upload = useUploadMailAttachment(reviewId);
  const remove = useDeleteMailAttachment(reviewId);

  const ackSet = useMemo(() => new Set(acknowledgedIndices), [acknowledgedIndices]);
  const groups = useMemo(
    () => createRequirementGroups(anforderungen),
    [anforderungen],
  );

  if (anforderungen.length === 0) return null;

  const toggle = (group: RequirementGroup) => {
    const next = new Set(ackSet);
    const groupIsAcked = group.indices.every((idx) => next.has(idx));
    group.indices.forEach((idx) => {
      if (groupIsAcked) next.delete(idx);
      else next.add(idx);
    });
    acknowledge.mutate(Array.from(next).sort((a, b) => a - b));
  };

  const uploadFiles = (files: FileList | File[]) => {
    Array.from(files).forEach((file) => upload.mutate(file));
  };

  const firstAttachmentGroupId = groups.find(canUseMailAttachment)?.id ?? null;

  return (
    <div
      id="requirements-checklist"
      className="scroll-mt-24 overflow-hidden rounded-md border border-border bg-surface xl:flex xl:h-full xl:flex-col"
    >
      <div className="flex items-center bg-muted px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        <span>Angebotsanforderungen</span>
      </div>
      <ul className="divide-y divide-border bg-surface xl:flex xl:flex-1 xl:flex-col">
        {groups.map((group) => {
          const checked = group.indices.every((idx) => ackSet.has(idx));
          const indeterminate =
            !checked && group.indices.some((idx) => ackSet.has(idx));
          return (
            <RequirementRow
              key={group.id}
              group={group}
              checked={checked}
              indeterminate={indeterminate}
              onToggle={() => toggle(group)}
              reviewId={reviewId}
              attachments={mailAttachments}
              showAttachmentList={group.id === firstAttachmentGroupId}
              onUploadFiles={uploadFiles}
              onRemoveAttachment={(fileName) => remove.mutate(fileName)}
              uploadPending={upload.isPending}
              removePending={remove.isPending}
              attachmentError={upload.isError || remove.isError}
            />
          );
        })}
      </ul>
    </div>
  );
}

function RequirementRow({
  group,
  checked,
  indeterminate,
  onToggle,
  reviewId,
  attachments,
  showAttachmentList,
  onUploadFiles,
  onRemoveAttachment,
  uploadPending,
  removePending,
  attachmentError,
}: {
  group: RequirementGroup;
  checked: boolean;
  indeterminate: boolean;
  onToggle: () => void;
  reviewId?: string;
  attachments: OutgoingMailAttachment[];
  showAttachmentList: boolean;
  onUploadFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (fileName: string) => void;
  uploadPending: boolean;
  removePending: boolean;
  attachmentError: boolean;
}) {
  const meta = KATEGORIE_META[group.category] ?? KATEGORIE_META.sonstige;
  const Icon = meta.icon;
  const uploadable = canUseMailAttachment(group);
  const disabled = !reviewId || uploadPending;
  const inputId = reviewId
    ? `mail-attachment-${reviewId}-${group.id}`
    : `mail-attachment-${group.id}`;

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { files } = event.currentTarget;
    if (files?.length) onUploadFiles(files);
    event.currentTarget.value = "";
  };

  return (
    <li className="flex items-start gap-2 px-3 py-1.5 xl:flex-1">
      <Checkbox
        checked={checked}
        indeterminate={indeterminate}
        onCheckedChange={onToggle}
        ariaLabel={`${group.title} bestätigen`}
        className="mt-0 h-5 w-5"
      />
      <Icon
        className={cn(
          "mt-0.5 h-3.5 w-3.5 shrink-0",
          checked ? "text-ek-blue" : "text-muted-foreground",
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1 xl:flex xl:flex-col xl:self-stretch">
        <div className="min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span
            className={cn(
              "text-sm font-semibold leading-tight",
              checked ? "text-muted-foreground" : "text-foreground",
            )}
          >
            {group.title}
          </span>
          <span className="rounded-full bg-muted/80 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {meta.label}
          </span>
          {group.posNrs.map((posNr) => (
            <PositionLink key={posNr} posNr={posNr} />
          ))}
        </div>
        {group.sourceQuotes.length > 0 && (
          <details className="group mt-0.5 xl:mt-auto xl:pt-1">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
              <ChevronRight
                className="h-3 w-3 transition-transform group-open:rotate-90"
                aria-hidden="true"
              />
              Quellen
            </summary>
            <ul className="mt-1.5 space-y-1 border-l border-border pl-3">
              {group.sourceQuotes.map((quote) => (
                <li
                  key={quote}
                  className="text-[11px] italic leading-snug text-muted-foreground"
                >
                  „{quote}“
                </li>
              ))}
            </ul>
          </details>
        )}
        {showAttachmentList && attachments.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {attachments.map((attachment) => (
              <li
                key={attachment.name}
                className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-1 text-[11px] text-muted-foreground"
              >
                <Paperclip className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="min-w-0 truncate">{attachment.name}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={removePending}
                  onClick={() => onRemoveAttachment(attachment.name)}
                  title="Zusatzanhang entfernen"
                  className="h-4 w-4 shrink-0 rounded-sm p-0"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {showAttachmentList && attachmentError && (
          <p className="mt-1 text-[11px] text-danger">
            Zusatzanhang konnte nicht aktualisiert werden.
          </p>
        )}
      </div>
      {uploadable && (
        <>
          <label
            htmlFor={disabled ? undefined : inputId}
            aria-disabled={disabled}
            title={attachmentButtonLabel(group.category)}
            className={cn(
              buttonVariants({ variant: "secondary", size: "sm" }),
              "h-7 shrink-0 cursor-pointer px-2 text-[11px]",
              disabled && "pointer-events-none opacity-50",
            )}
          >
            <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
            {uploadPending ? "Upload..." : "Anhängen"}
          </label>
          <input
            id={inputId}
            type="file"
            multiple
            className="sr-only"
            onChange={onFileChange}
            disabled={disabled}
          />
        </>
      )}
    </li>
  );
}

function canUseMailAttachment(group: RequirementGroup) {
  return ATTACHMENT_SOLVABLE_CATEGORIES.has(group.category);
}

function attachmentButtonLabel(category: AnforderungKategorie) {
  if (category === "zeichnung") return "Zeichnung anhängen";
  if (category === "zertifikat") return "Dokument anhängen";
  return "Anhang hinzufügen";
}

function createRequirementGroups(anforderungen: Anforderung[]) {
  const groups = new Map<string, RequirementGroup>();

  anforderungen.forEach((item, idx) => {
    const descriptor = resolveRequirementGroup(item);
    const group = groups.get(descriptor.id) ?? {
      ...descriptor,
      indices: [],
      sourceQuotes: [],
      posNrs: [],
    };

    group.indices.push(idx);
    addUnique(group.sourceQuotes, item.source_quote);
    if (typeof item.pos_nr === "number") {
      addUniqueNumber(group.posNrs, item.pos_nr);
    }
    groups.set(descriptor.id, group);
  });

  return Array.from(groups.values()).map((group) => ({
    ...group,
    posNrs: [...group.posNrs].sort((a, b) => a - b),
  }));
}

function resolveRequirementGroup(item: Anforderung): RequirementGroupDescriptor {
  const searchText = normalizeRequirementText(
    `${item.text} ${item.source_quote ?? ""}`,
  );
  const rule = REQUIREMENT_RULES.find((candidate) =>
    candidate.matches(item, searchText),
  );
  if (rule) {
    return {
      id: rule.id,
      title: rule.title,
      category: rule.category,
    };
  }

  const fallbackKey = normalizeRequirementText(item.text)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return {
    id: `${item.kategorie}-${fallbackKey || "anforderung"}`,
    title: item.text,
    category: item.kategorie,
  };
}

function normalizeRequirementText(value: string) {
  return value
    .toLocaleLowerCase("de-DE")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ß/g, "ss")
    .replace(/\s+/g, " ")
    .trim();
}

function addUnique(values: string[], value: string | null | undefined) {
  const normalized = value?.trim();
  if (normalized && !values.includes(normalized)) values.push(normalized);
}

function addUniqueNumber(values: number[], value: number) {
  if (!values.includes(value)) values.push(value);
}

function PositionLink({ posNr }: { posNr: number }) {
  const { reviewId } = useParams<{ reviewId: string }>();
  if (!reviewId) {
    return <span className="text-[11px] text-muted-foreground">→ Pos {posNr}</span>;
  }
  return (
    <Link
      to={`/reviews/${reviewId}/positions#pos-${posNr}`}
      className="text-[11px] text-brand hover:underline"
    >
      → Pos {posNr}
    </Link>
  );
}
