import { Link } from "react-router-dom";
import { ArrowRight, Bot, BarChart3, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function Home() {
  const { t } = useI18n();

  const FEATURES = [
    { icon: Bot, title: t.feat1, desc: t.feat1d },
    { icon: BarChart3, title: t.feat2, desc: t.feat2d },
    { icon: Zap, title: t.feat3, desc: t.feat3d },
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 bg-background">
      <div className="max-w-2xl text-center space-y-6">
        {/* Display Hero - 70px equivalent at display scale */}
        <h1 className="text-5xl md:text-[4.375rem] font-semibold tracking-normal text-foreground">
          {t.heroTitle}
        </h1>
        <p className="text-lg text-muted-foreground leading-relaxed">{t.heroDesc}</p>
        {/* Primary CTA - Wise Green with 16px radius */}
        <Link
          to="/agent"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-button bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors hover:scale-105 active:scale-95"
        >
          {t.startResearch} <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {/* Feature cards with generous border radius and warm styling */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-16 max-w-4xl w-full">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="bg-card rounded-card p-6 space-y-3 shadow-sm border border-border hover:shadow-md transition-shadow"
          >
            {/* Circular action button styling for icons */}
            <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
              <Icon className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-semibold text-foreground">{title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
