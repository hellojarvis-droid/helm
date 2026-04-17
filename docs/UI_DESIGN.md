# UI_DESIGN.md — Helm Design Principles

## 1. The Problem We're Solving (Design-Wise)

Serial entrepreneurs have seen every SaaS dashboard. They're fatigued. A premium tool earns its price through *feel*, not feature count. Denovo gets several things right — we'll steal them — and gets a few things wrong — we'll fix them.

## 2. What We're Stealing from Denovo

Based on their current product and Product Hunt reception:

- **Single-studio metaphor.** Every business lives inside a "Studio" containing all assets. This is the correct mental model. We adopt it but call ours "Businesses" because serial entrepreneurs think in businesses, not studios.
- **8-minute-to-live speed claim.** Denovo leads with speed. We should too — but we back it up with proof (countdown timer during launch showing each agent completing).
- **AI co-founder framing.** "Talk to it like a partner" is the right metaphor. Not "chatbot," not "assistant." We lean into this harder with the CEO Agent naming.
- **Remix-my-idea feature.** Denovo lets you fork someone else's business concept. We add this in v2 for the portfolio tier — a "templates" section curated by Helm's top users.
- **One-page summary card** for each business concept. Good format. We'll use a similar density but with better typography.

## 3. Where Denovo Falls Short (and We Improve)

From Product Hunt Q&A, common startup-AI-tool feedback, and typical AI product complaints:

| Denovo weakness | Helm improvement |
|---|---|
| Dashboard UX feels like a SaaS template — sidebar, cards, tabs | Conversation-first. The chat is always the primary surface. Dashboards are on a second tab, not the home. |
| Web-first, mobile is an afterthought | Mobile-first. The app is the product. Web is the deep-dive. |
| Pricing ($25/mo Pro) signals "low-stakes side project" | Premium pricing ($199+) signals a serious tool. |
| Content-marketing feel (blog posts templated "How to start a X business") | We don't SEO-farm. Our marketing is craft content, not volume. |
| "Templated" feel in generated assets | Our Creative Director agent explicitly avoids template language. Brand voice tests enforce distinctiveness. |
| Exception handling is unclear ("what happens when a supplier changes terms?") | Explicit escalation surface. Every agent flags + routes + logs. User sees "3 things need your attention" on mobile home. |
| Generic approval flow (click button, done) | Rich approval cards with expected outcome, reversibility, and "Why?" explanations. |
| No spend control visibility | One-tap total-spend view on mobile home. Live Activity on lock screen during peak hours. |
| Agents feel like one blob | Named specialists with distinct visual identities. Users can see "Ads Operator paused 2 campaigns" rather than "AI did a thing." |

## 4. Premium Feel — Specific Principles

### 4.1 Motion matters more than color

Generic AI tools have loud colors and static layouts. Premium tools have restrained palettes and expressive motion.

- Every state transition is animated (spring physics, never linear).
- Approval cards have a subtle breathing animation when pending.
- The CEO Agent's "thinking" state shows a custom indicator, not a spinner.
- Haptics on iOS for approvals, wins, and alerts. Android equivalent via vibration.
- Live Activity on iOS lock screen shows today's revenue and any pending approval. Tap to expand.

### 4.2 Typography carries the weight

- **Mobile:** SF Pro Rounded (iOS) / Inter Tight (Android). Generous line-height. Numbers in a tabular-figures font so dollar amounts don't jump.
- **Desktop + Web:** A custom pairing. Proposed: **Söhne** (display + body) + **JetBrains Mono** (numbers, code). Fallback: Inter + IBM Plex Mono if Söhne licensing isn't worth it.
- One type scale, used consistently. 9 sizes, not 47.
- **Copy voice:** direct, confident, warm. No em-dashes in UI copy. No "Let's!" No "Awesome!" No emojis in system UI (emojis are fine in user-generated content).

### 4.3 Color palette

Premium means restrained. Think Linear, Vercel, Rauno's work — not AWS, not Stripe Dashboard's aggressive blues.

**Working palette (placeholder until brand work):**
- **Ink** `#0A0A0A` — primary text, deep backgrounds
- **Paper** `#FAFAF8` — primary light background
- **Haze** `#F3F2EE` — elevated surfaces (cards, inputs)
- **Iron** `#6B6B6B` — secondary text
- **Accent** `#E85D1A` — one bold accent color used sparingly (approvals, CTAs, live indicators). A warm burnt orange — distinct from every competitor's blue.
- **Success** `#2D8659` — gains, confirmations
- **Warning** `#B8860B` — pending states
- **Error** `#A8251A` — crashes, ROAS below threshold

Dark mode is not optional. Most serial entrepreneurs work at night.

### 4.4 Density

Denovo's mistake: dashboard-style density with lots of numbers on screen. Helm's approach:

- **Mobile home** shows ~3 numbers: today's revenue, today's spend, pending approvals. Everything else is one tap away.
- **Chat** is full-bleed. No chrome above or below. The approval cards *are* the UI.
- **Desktop** uses a three-column layout: business switcher (left), chat (center), current business detail (right). Collapsible.
- **Web dashboard** can have density — this is the deep-dive surface.

### 4.5 No "loading" states

Instead of spinners, show the agent doing work. "Product Builder: configuring Shopify theme… Creative Director: generating hero image…" as a streaming log. Makes the wait feel productive and builds trust.

## 5. Component System

- Base: **shadcn/ui** (web + desktop). Adopt wholesale, then customize.
- Mobile: build our own in React Native with the same design tokens. No NativeBase, no Paper — their feel is generic.
- Design tokens live in `packages/design-tokens` as JSON. Consumed by all surfaces. Changes propagate everywhere.
- Icons: **Lucide** (consistent, open, well-maintained). Custom icons for Helm-specific concepts (each specialist agent has a distinct icon).

## 6. The Chat Surface (Critical — Get This Right)

This is where the user lives. The biggest UX risk in the whole product is a chat that feels like every other LLM chat.

### What we do differently from ChatGPT/Claude.ai:

- **Messages are threaded by business.** When user says "launch a new store," a new thread forks. They can jump between threads via a compact switcher at the top.
- **Agent actions are inline artifacts, not walls of text.** When the Product Builder finishes the Shopify store, the message IS a store preview card with the URL, key config, and a "Tap to inspect" affordance. Not "I finished setting up your Shopify store. Here's what I did: [1000 words]."
- **The "Why?" affordance on every agent action.** Expandable inline explanation, 2-3 sentences, plus a link to the full trace for power users.
- **Approval cards are not text.** They're first-class UI primitives with Approve/Modify/Deny/Why? buttons.
- **Specialist agents have visible identity.** When Creative Director speaks, you see a small Creative Director avatar + label. Builds trust ("I know who's doing what").
- **Voice input is a core input, not a feature.** Hold-to-talk with live transcription.
- **Paste is smart.** Paste a URL and Helm unfurls it. Paste an image and the relevant agent picks it up (e.g., a product photo goes to Creative Director as reference).

## 7. The Dashboard (Web / Desktop Detail)

For when the user wants numbers, not chat.

**Sections, in order of importance:**

1. **Today** — KPIs for today across all active businesses. One screen, no scrolling.
2. **Businesses** — list with mini-KPIs. Click into one for the full drill-down.
3. **Agents** — live view of what each specialist is doing right now. Watchable.
4. **Approvals** — queue. Pending, resolved.
5. **Money** — the financial deep-dive. Stripe-style charts but simpler.
6. **Events** — the agent event log, filterable. For power users and debugging.
7. **Settings** — billing, integrations, kill switch, preferences.

Defaults to **Today** on open. Never defaults to Settings.

## 8. Onboarding

The single highest-stakes design moment. First 90 seconds determine whether the user ever comes back.

**Goal:** user creates their first business and feels the magic within 10 minutes of signup.

**Flow:**
1. **Sign up with Clerk** (email or Google). 10 seconds.
2. **Welcome screen** — 3 sentences, not 30. "You're going to talk to your CEO Agent. It'll ask what kind of business you want to run. Then it'll build it. You'll approve the important stuff from your phone."
3. **Connect payment** — one credit card for Helm's subscription. Can defer actual business funding until later.
4. **Agree to agent autonomy terms** — short, plain English, not a 12-page ToS. A human-readable summary + link to full terms.
5. **Set a default budget** — "How much per month are you comfortable spending per business?" (slider from $500 to $20k). This becomes the default cap for all businesses.
6. **Install the mobile app** — QR code, takes 30s. Required to proceed past this point.
7. **First conversation with CEO Agent** — voice or text: "What kind of business do you want to start?" User responds. Idea Scout returns 3 options.
8. **User picks one, taps "Let's launch."** Countdown UI begins.
9. **Launch theater** — 8-15 minutes, full-screen, narrated by the CEO Agent. User sees each specialist completing its work live. Haptics on each completion. When done, confetti + "Your store is live."
10. **First approval card** — "Approve $300 for first week of Meta ads?" Tap.

After this, the user is home. Pull-to-refresh reveals today's first events.

## 9. Accessibility & Inclusivity (Non-Negotiable)

- WCAG 2.2 AA minimum on web and desktop.
- Full voice control on mobile (dictation + TTS output).
- Localization: ship English at launch. Spanish, Portuguese within 6 months (LatAm is a big entrepreneur market).
- No color-only signaling (always has an icon or label).
- Dark mode is first-class.
- Respect `prefers-reduced-motion`.

## 10. Prohibited Design Choices

Don't. Ever. Do these:

- ❌ Hamburger menu as primary navigation on mobile.
- ❌ Toast notifications for important information. Notifications are too important to be transient.
- ❌ "New!" badges that never go away.
- ❌ Cookie banners on our marketing site (we're fine with privacy-respecting analytics — Plausible or PostHog self-hosted).
- ❌ Chat suggestion chips ("Try asking…"). Patronizing.
- ❌ Emoji in system messages.
- ❌ Confirming that a confirm happened. ("Yes, that was confirmed!")
- ❌ The word "Dashboard" in the UI. It's a dashboard. We don't need to label it.
- ❌ The word "AI" in user-facing copy. They know. Say "the CEO Agent" or "Ads Operator," not "our AI."
- ❌ Spinners. Show actual progress.

## 11. Reference Products for Look and Feel

- **Linear** — typography, motion, restraint.
- **Arc** — boldness, brand confidence.
- **Raycast** — command palette, speed, keyboard-first.
- **Things 3** — mobile density, joy in details.
- **Superhuman** — premium email; the "feels fast" feeling.
- **Ramp** — spend management UX done right (inspiration for our Money section).
- **Mercury** — premium fintech UI for solo founders.

Study these before designing any new screen.

## 12. Launch Collateral

The marketing site is where the premium signal starts. Build it with the same level of craft as the product. Single page, video-forward, no "enterprise" bloat. Reference: the early Linear site. Product tour is a 60-second video of the CEO Agent launching a business in real time — not a "click to reveal" feature walk-through.
