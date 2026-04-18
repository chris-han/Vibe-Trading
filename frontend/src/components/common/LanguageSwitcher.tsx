import React from "react";
import { useI18n } from "@/lib/i18n";

export function LanguageSwitcher() {
  const { lang, setLang } = useI18n();
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setLang("en")}
        className={"px-2 py-1 text-xs rounded " + (lang === "en" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted")}
        aria-pressed={lang === "en"}
      >
        EN
      </button>
      <button
        onClick={() => setLang("zh")}
        className={"px-2 py-1 text-xs rounded " + (lang === "zh" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted")}
        aria-pressed={lang === "zh"}
      >
        中
      </button>
    </div>
  );
}

export default LanguageSwitcher;
