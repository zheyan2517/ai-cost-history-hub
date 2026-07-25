import { create } from "zustand";
import { toast } from "sonner";
import { storageAdapter } from "@/services/storage";
import i18n from "../i18n";
import type { SupportedLanguage } from "../i18n";

interface LanguageStore {
  language: SupportedLanguage;
  isLoading: boolean;
  setLanguage: (language: SupportedLanguage) => Promise<void>;
  loadLanguage: () => Promise<void>;
}

/** Product UI is English-only. */
const getSupportedLanguage = (_lang?: string): SupportedLanguage => "en";

export const useLanguageStore = create<LanguageStore>((set) => ({
  language: "en",
  isLoading: true,

  setLanguage: async (language) => {
    const next = getSupportedLanguage(language);
    await i18n.changeLanguage(next);
    set({ language: next });

    try {
      const store = await storageAdapter.load("settings.json", {
        defaults: {},
        autoSave: true,
      });
      await store.set("language", next);
      await store.save();
    } catch {
      toast.error(i18n.t("common.settings.language.saveFailed"));
    }
  },

  loadLanguage: async () => {
    set({ isLoading: true });
    try {
      await i18n.changeLanguage("en");
      try {
        const store = await storageAdapter.load("settings.json", {
          defaults: {},
          autoSave: true,
        });
        await store.set("language", "en");
        await store.save();
      } catch {
        // store optional
      }
      localStorage.setItem("i18nextLng", "en");
      set({ language: "en" });
    } catch (error) {
      console.error("Failed to load language:", error);
      set({ language: "en" });
    } finally {
      set({ isLoading: false });
    }
  },
}));
