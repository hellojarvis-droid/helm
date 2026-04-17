# PRD — Helm Product Requirements

## 1. Who This Is For

**Primary persona: The serial entrepreneur.** Has launched 2+ businesses. Technical enough to understand what agents do but doesn't want to be the one doing it. Values their time at $500+/hour. Runs multiple projects in parallel. Owns the brand and the P&L, but delegates execution. Currently operating across 8-15 SaaS tools per business and hating it.

**Secondary persona: The aspiring serial entrepreneur.** Has launched 1 business (maybe unsuccessfully). Has the instinct and the drive but keeps getting stuck in execution. Will become primary persona once the platform works.

**Explicitly not our target:** First-time founders looking to validate an idea cheaply (Denovo has that covered at $25/mo). Enterprise teams. Agencies operating businesses *for* other people (that's a v2 expansion).

## 2. The Promise

*"Tell Helm what business you want to build. In 15 minutes, you have a live storefront, a first ad campaign running, and agents monitoring your sales while you sleep. Tell it which direction to grow. Approve the spend you want to approve. Everything else runs itself — and you can steer from your phone."*

## 3. The Three Surfaces (and Why Each Exists)

### 3.1 Mobile — the command surface
The place the user actually lives. What they use 80% of the time.

- One persistent chat with the CEO Agent. No tabs.
- Voice-first input. Talk while walking the dog.
- Push notifications that are *approval cards*, not noise. Each card has Approve / Modify / Deny / Explain buttons.
- A "Today" view: revenue, ad spend, pending approvals, 3 overnight wins.
- A multi-business switcher that feels fast, not nested.
- iOS Live Activity on the lock screen showing today's P&L during peak sales hours.

### 3.2 Desktop — the execution surface
The place where agents do work that needs a screen.

- Runs Tauri, native feel, small binary.
- Tight integration with Claude's computer-use capabilities for any task that needs browser control (e.g., a TikTok account setup flow that doesn't have an API).
- Shows live agent activity — you can literally watch Creative Director generating ad variants.
- Plays the same chat as mobile, but richer: inline artifacts, diffs, previews.
- Optional: dock in the menu bar for always-on status.

### 3.3 Web — the analytics and admin surface
The place where the user does deep work: strategy review, historical analysis, multi-business P&L, team invites.

- Full dashboard per business + holding-company view.
- Agent observability: every action, trace, decision.
- Approval history and reversibility.
- Billing and settings.
- Next.js, server-rendered, fast.

**The same chat thread runs across all three surfaces.** Dispatch-style. Start a conversation on mobile, continue on desktop, review the result on web.

## 4. The Core User Journey (End-to-End)

### 4.1 First-time: "Start my first business"

1. **Onboarding (mobile, 3 min):** Sign up with Clerk. Connect one credit card to fund the platform. Accept the terms on agent autonomy and spend limits. Set a default monthly business budget.
2. **Ideation (mobile, 2 min):** Voice-brain-dump: "I want a physical-product side business, US market, under $50 retail, something I could be proud to put on my LinkedIn."
   - Idea Scout agent returns 3 concepts, each with: proven-demand signals (Reddit discussions, TikTok trend volume, Amazon BSR movement), estimated unit economics, sample products from vetted suppliers, and why it fits the user.
   - User picks one with a tap.
3. **Launch (mixed, 8-15 min, mostly agent-side):**
   - Finance agent creates a Stripe connected account for the new business, issues a virtual card with a $500 weekly spend cap, auto-approved merchant categories (Meta Ads, Google Ads, TikTok, domain registrars, Shopify, supplier APIs).
   - Product Builder spins up the Shopify store, buys the domain, sets up a theme, loads 5-10 products from a supplier (Printful for POD or CJ Dropshipping), configures shipping zones.
   - Creative Director generates the brand (logo, palette, voice), writes product descriptions, generates first-pass product photography via image gen.
   - Marketing Strategist drafts the 30-day plan: channel mix, creative angles, budget pacing.
   - The CEO Agent pushes one summary card to the user's phone: "Your store is live at [url]. Here's what I did. Approve $300 for first-week Meta ads?"
4. **Operation (ongoing, mostly hands-off):**
   - Daily: Social Engagement agent replies to comments/DMs. Creative Director produces 3-5 new ad variants. Ads Operator pushes winners live and kills losers after 48h.
   - Weekly: Growth Analyst runs a review, proposes next-week budget allocations, flags anomalies.
   - Monthly: Finance agent generates a P&L, sends to the user's email, updates QuickBooks via Composio.
   - Anytime: CS agent handles order questions and escalates refunds above threshold.

### 4.2 Returning user: "Launch another one"

1. On mobile: "Start another business, this time dog accessories, different account to my candle store."
2. Entire loop repeats. New Stripe connected account, new card, new Shopify store, new ad accounts.
3. Dashboard now shows a 2-business holding-company view.

### 4.3 Crisis: "My ROAS is crashing"

1. Growth Analyst detects anomaly: ROAS dropped from 3.2 to 1.4 over 72h.
2. Pushes a red approval card to the user's phone: "Candle store ROAS crashed. Probable cause: iOS 18 attribution lag after Meta update. Recommended action: pause 3 underperforming campaigns, shift $200/day to top performer, launch 2 new creative tests. Approve or modify?"
3. User taps Approve. Ads Operator executes. Growth Analyst schedules a 48h check-in.

## 5. Feature List (In Priority Order)

### P0 — Must Ship Before Public Launch

- [ ] Account creation + multi-business support
- [ ] Stripe Connect + Issuing flow with spend controls
- [ ] CEO Agent orchestrator (Claude Opus 4.7)
- [ ] Idea Scout, Product Builder, Creative Director, Ads Operator, Finance, Growth Analyst specialist agents
- [ ] Composio integration for 20+ essential toolkits (see `docs/INTEGRATIONS.md`)
- [ ] Shopify store creation + product loading
- [ ] Meta Ads campaign creation + management
- [ ] Daily digest generation + push to phone
- [ ] Approval card UX on mobile
- [ ] Full chat sync across mobile / desktop / web
- [ ] Agent event log + replay
- [ ] Emergency pause-all-agents kill switch
- [ ] Basic billing (Stripe Billing for Helm subscription)

### P1 — Ship Within 30 Days of P0

- [ ] Social Engagement agent (Instagram, TikTok, X replies)
- [ ] CS agent (Gorgias or Intercom via Composio)
- [ ] Desktop app with computer use
- [ ] iOS Live Activity
- [ ] Voice input (Whisper)
- [ ] Google Ads + TikTok Ads support
- [ ] Proprietary trend data (TikTok, Reddit, Amazon BSR) for Idea Scout
- [ ] Email agent (Klaviyo via Composio)
- [ ] Weekly strategic review email

### P2 — Shipped When It Earns Priority

- [ ] SaaS vertical support (not just DTC)
- [ ] Team invites (bring in a human operator per business)
- [ ] Custom skills marketplace
- [ ] Plaid integration for non-Stripe banking
- [ ] Native Swift/Kotlin rewrites
- [ ] White-label for agencies

## 6. What Premium Means (Specific, Not Vague)

- **One conversation, not 47 tabs.** The UX is a single thread. Every screen pulls from that thread's state. No navigating to "Ad Campaigns > Active > Campaign #3" to check status. Ask the agent.
- **Approval cards feel expensive.** Cards have haptics, smooth motion, clear consequences spelled out before the user taps. Example card content: "Spending $340 on 3 TikTok creatives targeting ages 25-34 interested in home decor. Expected ROAS: 2.1-2.8. Budget impact: 28% of remaining weekly. If ROAS < 1.5 after 48h, I'll pause and recommend."
- **Defaults are opinionated.** Helm picks a typography, a palette, a shipping policy, a return policy. The user overrides, not originates. Denovo's weakness is feeling like a blank slate that asks 40 questions; Helm's strength is assuming the right answer and asking permission to deviate.
- **Nothing is "coming soon."** If a feature is in the product, it works. If it doesn't work yet, it isn't visible.
- **Explanations on demand.** Every agent action has a "Why?" button that opens a short, well-written explanation. No wall of JSON. No LLM trace dumps. A human sentence or three.
- **Brand-level consistency across devices.** The candle store the user launches has a coherent visual identity on the storefront, in the ads, in the emails, in the packaging — because one Creative Director agent owns it end-to-end, not five different tools.

## 7. Pricing

Premium positioning is a pricing strategy, not just a design choice.

| Tier | Price | Target | Included |
|---|---|---|---|
| **Founder** | $199/mo | First-time user testing the platform | 1 business, full agent swarm, $50/mo token + Managed Agents session-hour budget included |
| **Operator** | $499/mo | The serial entrepreneur with 2-4 concurrent businesses | 5 businesses, priority model access, $200/mo included usage, first-party human-in-the-loop slot |
| **Portfolio** | $1,999/mo | The 5+ business operator, likely revenue >$500k | Unlimited businesses, white-glove onboarding, custom skills, direct Anthropic partner ops |

Usage overage is billed at cost + 20%. Stripe Issuing float interest accrues to Helm (this is a meaningful revenue stream at scale — don't skip it).

## 8. Success Metrics (What We'll Actually Watch)

**Activation:** User launches first business within 24h of signup. Target: 70%.

**First revenue:** First dollar in the first business's Stripe account within 14 days. Target: 40%.

**Agent trust score:** % of approval cards the user approves unmodified. Target: 65% by day 30. If this is low, the agents are proposing bad plans.

**Multi-business adoption:** % of users who launch a 2nd business within 60 days. Target: 30%. This is the serial-entrepreneur signal.

**90-day retention:** % still paying at day 90. Target: 75%.

**NPS:** Target 50+ for the Operator and Portfolio tiers.

## 9. What We're Explicitly Not Doing

- **We're not a hosting platform.** Shopify hosts the store. Fly.io hosts our backend. We don't run other people's websites.
- **We're not a bank.** Stripe is. We issue cards through Stripe Issuing under Stripe's BIN-sponsor banks. We don't take custody of funds.
- **We're not an ads agency.** Meta's AI does the bidding. We orchestrate budget allocation and creative production.
- **We're not a design tool.** Figma exists. Our Creative Director uses image/video generation APIs — it doesn't replicate Figma.
- **We're not legal counsel.** Users need a real lawyer for LLC formation, trademark, etc. We can recommend services (Stripe Atlas) but we don't issue legal advice.

## 10. Open Questions for the User

(Don't stop building for these — assume a reasonable default and flag.)

1. **Name.** Is "Helm" the final name or working? If final, we need to verify domain availability.
2. **Legal entity.** Will Helm, Inc. be the merchant of record for the Stripe Issuing program? (High compliance implications.)
3. **Geographic scope at launch.** US only (Stripe Issuing is mostly US-centric)? Or also UK/EU?
4. **Vertical breadth at public launch.** DTC only, or also SaaS/services?
5. **Early access plan.** Private beta with ~50 serial entrepreneurs before public launch?
