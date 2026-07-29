/**
 * General settings editor.
 *
 * This section is intentionally small and uses the same controlled update
 * contract as the other settings sections. Unknown settings remain available
 * through JSON mode in SettingsEditorPane.
 */

import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ChevronDown, ChevronRight, Settings2 } from "lucide-react";
import type { AutoUpdatesChannel, ClaudeCodeSettings, ClaudeModel } from "@/types";

interface GeneralSectionProps {
  settings: ClaudeCodeSettings;
  isExpanded: boolean;
  onToggle: () => void;
  onChange: (updates: Partial<ClaudeCodeSettings>) => void;
  readOnly: boolean;
}

interface ToggleRowProps {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  readOnly: boolean;
  onCheckedChange: (checked: boolean) => void;
}

const ToggleRow: React.FC<ToggleRowProps> = ({
  id,
  label,
  description,
  checked,
  readOnly,
  onCheckedChange,
}) => (
  <div className="flex items-center justify-between gap-4 rounded-md border border-border/50 p-3">
    <div className="min-w-0">
      <Label htmlFor={id} className="text-sm font-medium">
        {label}
      </Label>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
    <Switch
      id={id}
      checked={checked}
      disabled={readOnly}
      onCheckedChange={onCheckedChange}
    />
  </div>
);

export const GeneralSection: React.FC<GeneralSectionProps> = React.memo(({
  settings,
  isExpanded,
  onToggle,
  onChange,
  readOnly,
}) => {
  const { t } = useTranslation();
  const model = settings.model ?? "sonnet";
  const updateAttribution = (field: "commit" | "pr", value: string) => {
    const attribution = { ...settings.attribution, [field]: value || undefined };
    onChange({ attribution });
  };

  return (
    <Collapsible open={isExpanded} onOpenChange={() => onToggle()}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="w-full justify-start gap-2 px-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          <Settings2 className="h-4 w-4" />
          <span>{t("settingsManager.general.behavior")}</span>
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 px-3 pb-4 pt-2">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t("settingsManager.general.modelLanguage")}</Label>
            <Select
              value={model}
              disabled={readOnly}
              onValueChange={(value) => onChange({ model: value as ClaudeModel })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="opus">Opus</SelectItem>
                <SelectItem value="sonnet">Sonnet</SelectItem>
                <SelectItem value="haiku">Haiku</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="general-language">{t("settingsManager.general.language")}</Label>
            <Input
              id="general-language"
              value={settings.language ?? ""}
              disabled={readOnly}
              placeholder={t("settingsManager.general.languagePlaceholder")}
              onChange={(event) => onChange({ language: event.target.value || undefined })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="general-output-style">{t("settingsManager.general.outputStyle")}</Label>
            <Input
              id="general-output-style"
              value={settings.outputStyle ?? ""}
              disabled={readOnly}
              placeholder={t("settingsManager.general.outputStylePlaceholder")}
              onChange={(event) => onChange({ outputStyle: event.target.value || undefined })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="general-plans-directory">{t("settingsManager.general.plansDirectory")}</Label>
            <Input
              id="general-plans-directory"
              value={settings.plansDirectory ?? ""}
              disabled={readOnly}
              onChange={(event) => onChange({ plansDirectory: event.target.value || undefined })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="general-cleanup-days">{t("settingsManager.general.cleanupPeriod")}</Label>
            <Input
              id="general-cleanup-days"
              type="number"
              min={0}
              value={settings.cleanupPeriodDays ?? ""}
              disabled={readOnly}
              onChange={(event) => {
                const value = event.target.value;
                onChange({
                  cleanupPeriodDays: value === "" ? undefined : Math.max(0, Number(value)),
                });
              }}
            />
          </div>

          <div className="space-y-2">
            <Label>{t("settingsManager.general.autoUpdatesChannel")}</Label>
            <Select
              value={settings.autoUpdatesChannel ?? "stable"}
              disabled={readOnly}
              onValueChange={(value) => onChange({ autoUpdatesChannel: value as AutoUpdatesChannel })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stable">{t("settingsManager.general.channelStable")}</SelectItem>
                <SelectItem value="latest">{t("settingsManager.general.channelLatest")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          <ToggleRow
            id="general-thinking"
            label={t("settingsManager.general.alwaysThinking")}
            description={t("settingsManager.general.alwaysThinkingDesc")}
            checked={settings.alwaysThinkingEnabled === true}
            readOnly={readOnly}
            onCheckedChange={(checked) => onChange({ alwaysThinkingEnabled: checked })}
          />
          <ToggleRow
            id="general-gitignore"
            label={t("settingsManager.general.respectGitignore")}
            description={t("settingsManager.general.respectGitignoreDesc")}
            checked={settings.respectGitignore !== false}
            readOnly={readOnly}
            onCheckedChange={(checked) => onChange({ respectGitignore: checked })}
          />
          <ToggleRow
            id="general-turn-duration"
            label={t("settingsManager.general.showTurnDuration")}
            description={t("settingsManager.general.showTurnDurationDesc")}
            checked={settings.showTurnDuration !== false}
            readOnly={readOnly}
            onCheckedChange={(checked) => onChange({ showTurnDuration: checked })}
          />
          <ToggleRow
            id="general-spinner-tips"
            label={t("settingsManager.general.spinnerTips")}
            description={t("settingsManager.general.spinnerTipsDesc")}
            checked={settings.spinnerTipsEnabled !== false}
            readOnly={readOnly}
            onCheckedChange={(checked) => onChange({ spinnerTipsEnabled: checked })}
          />
          <ToggleRow
            id="general-terminal-progress"
            label={t("settingsManager.general.terminalProgressBar")}
            description={t("settingsManager.general.terminalProgressBarDesc")}
            checked={settings.terminalProgressBarEnabled !== false}
            readOnly={readOnly}
            onCheckedChange={(checked) => onChange({ terminalProgressBarEnabled: checked })}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="general-commit-attribution">{t("settingsManager.general.commitAttribution")}</Label>
            <Input
              id="general-commit-attribution"
              value={settings.attribution?.commit ?? ""}
              disabled={readOnly}
              onChange={(event) => updateAttribution("commit", event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="general-pr-attribution">{t("settingsManager.general.prAttribution")}</Label>
            <Input
              id="general-pr-attribution"
              value={settings.attribution?.pr ?? ""}
              disabled={readOnly}
              onChange={(event) => updateAttribution("pr", event.target.value)}
            />
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
});

GeneralSection.displayName = "GeneralSection";
