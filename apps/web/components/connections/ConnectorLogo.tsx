"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { ConnectorInfo } from "@/lib/api";

type Tier = "primary" | "favicon" | "fallback";

// Brands Simple Icons removed for trademark reasons (most Microsoft
// products, Slack, Salesforce, LinkedIn, etc.). Each key is our canonical
// icon_slug; the value is an Iconify path that returns a colored SVG of
// the brand mark. Slugs not listed here go through the Simple Icons CDN.
// Slugs not on either route fall through to the favicon tier.
const ICONIFY_OVERRIDES: Record<string, string> = {
  slack: "logos:slack-icon",
  salesforce: "logos:salesforce",
  pipedrive: "logos:pipedrive",
  linkedin: "logos:linkedin-icon",
  microsoftteams: "logos:microsoft-teams",
  microsoftonedrive: "logos:microsoft-onedrive",
  microsoftsharepoint: "streamline-logos:microsoft-sharepoint-logo-solid",
  canva: "devicon:canva",
  amazon: "streamline-color:amazon-flat",
};

function primaryLogoUrl(slug: string): string {
  const iconify = ICONIFY_OVERRIDES[slug];
  if (iconify) return `https://api.iconify.design/${iconify}.svg`;
  return `https://cdn.simpleicons.org/${slug}`;
}

function pickInitialTier(connector: ConnectorInfo): Tier {
  if (connector.icon_slug) return "primary";
  if (hostnameFrom(connector.signup_url)) return "favicon";
  return "fallback";
}

function hostnameFrom(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

const CATEGORY_TONE: Record<string, string> = {
  Creative: "from-terracotta to-amber",
  Commerce: "from-sage to-amber",
  Payments: "from-ink to-terracotta",
  Ads: "from-terracotta to-rose",
  Social: "from-sage to-terracotta",
  Ops: "from-ink-2 to-sage",
  Communication: "from-amber to-sage",
};

// Renders a connector's brand mark. Tries, in order:
//   1. Iconify `logos` collection (for brands Simple Icons removed) or
//      Simple Icons CDN, depending on the slug
//   2. Google's favicon service against the connector's signup_url host
//   3. Category-tinted gradient with the brand's first letter
// img-src in next.config CSP already allows arbitrary https hosts, so
// hotlinking both CDNs is safe.
export function ConnectorLogo({
  connector,
  size = 40,
}: {
  connector: ConnectorInfo;
  size?: number;
}) {
  const [tier, setTier] = useState<Tier>(() => pickInitialTier(connector));
  const inner = Math.round(size * 0.55);
  const host = hostnameFrom(connector.signup_url);

  const wrapper = cn(
    "grid place-items-center rounded-md shrink-0 overflow-hidden",
    tier === "fallback"
      ? cn(
          "bg-gradient-to-br text-paper font-serif leading-none",
          CATEGORY_TONE[connector.category] ?? "from-ink to-ink-2",
        )
      : "bg-paper-2 border border-rule",
  );
  const wrapperStyle = { width: size, height: size, fontSize: Math.round(size * 0.45) };

  if (tier === "primary" && connector.icon_slug) {
    return (
      <div className={wrapper} style={wrapperStyle}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={primaryLogoUrl(connector.icon_slug)}
          alt={`${connector.name} logo`}
          width={inner}
          height={inner}
          style={{ width: inner, height: inner }}
          className="object-contain"
          loading="lazy"
          onError={() => setTier(host ? "favicon" : "fallback")}
        />
      </div>
    );
  }

  if (tier === "favicon" && host) {
    return (
      <div className={wrapper} style={wrapperStyle}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`https://www.google.com/s2/favicons?domain=${host}&sz=128`}
          alt={`${connector.name} logo`}
          width={inner}
          height={inner}
          style={{ width: inner, height: inner }}
          className="object-contain"
          loading="lazy"
          onError={() => setTier("fallback")}
        />
      </div>
    );
  }

  return (
    <div className={wrapper} style={wrapperStyle}>
      {connector.name[0]}
    </div>
  );
}
