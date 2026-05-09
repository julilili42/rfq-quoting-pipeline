import { Save } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/cn";

interface SaveBarProps {
  isDirty: boolean;
  saving: boolean;
  saveSuccess: boolean;
  saveError: unknown;
}

export function SaveBar({ isDirty, saving, saveSuccess, saveError }: SaveBarProps) {
  return (
    <div className="sticky bottom-0 z-10 -mx-4 border-t border-border bg-background/90 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <span
          className={cn(
            "text-xs text-muted-foreground transition-opacity",
            isDirty ? "opacity-100" : "opacity-0",
          )}
        >
          Ungespeicherte Änderungen
        </span>
        <div className="flex items-center gap-3">
          {saveSuccess && !isDirty && (
            <span className="text-xs font-medium text-success">Gespeichert</span>
          )}
          {saveError != null && (
            <span className="text-xs font-medium text-danger">Speichern fehlgeschlagen</span>
          )}
          <Button variant="primary" type="submit" disabled={saving || !isDirty}>
            <Save className="h-4 w-4" aria-hidden="true" />
            {saving ? "Speichere…" : "Speichern"}
          </Button>
        </div>
      </div>
    </div>
  );
}
