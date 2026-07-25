import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// English-only product UI
import enCommon from "./locales/en/common.json";
import enAnalytics from "./locales/en/analytics.json";
import enSession from "./locales/en/session.json";
import enSettings from "./locales/en/settings.json";
import enTools from "./locales/en/tools.json";
import enError from "./locales/en/error.json";
import enMessage from "./locales/en/message.json";
import enRenderers from "./locales/en/renderers.json";
import enUpdate from "./locales/en/update.json";
import enFeedback from "./locales/en/feedback.json";
import enRecentEdits from "./locales/en/recentEdits.json";
import enArchive from "./locales/en/archive.json";
import enWebui from "./locales/en/webui.json";

export const supportedLanguages = {
  en: "English",
} as const;

export type SupportedLanguage = keyof typeof supportedLanguages;

export const languageLocaleMap: Record<string, string> = {
  en: "en-US",
};

export const namespaces = [
  "common",
  "analytics",
  "session",
  "settings",
  "tools",
  "error",
  "message",
  "renderers",
  "update",
  "feedback",
  "recentEdits",
  "archive",
  "webui",
] as const;

export type Namespace = (typeof namespaces)[number];

type TranslationValue = string | string[];
function mergeNamespaces(
  ...nsObjects: Record<string, TranslationValue>[]
): Record<string, TranslationValue> {
  return Object.assign({}, ...nsObjects);
}

const resources = {
  en: {
    translation: mergeNamespaces(
      enCommon,
      enAnalytics,
      enSession,
      enSettings,
      enTools,
      enError,
      enMessage,
      enRenderers,
      enUpdate,
      enFeedback,
      enRecentEdits,
      enArchive,
      enWebui
    ),
  },
};

void i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  defaultNS: "translation",
  ns: ["translation"],
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;

export { useAppTranslation } from "./useAppTranslation";
export type { TranslationKey, TranslationPrefix } from "./types.generated";
