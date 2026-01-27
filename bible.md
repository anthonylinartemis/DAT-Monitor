# Prometheus ETF Project Bible

## Philosophy

> This codebase will outlive you. Every shortcut becomes someone else's burden. Fight entropy and make things better than where you left it.

---

## The Prime Directive: Long-Term Stewardship

We do not build for today; we build for the engineers (and AIs) of five years from now. Technical debt is a high-interest loan that eventually bankrupts a project. Every line of code must be written with the assumption that it will be read and maintained by someone who is **tired**, **in a rush**, and **lacks your current context**.

---

## Core Engineering Pillars

### 1. Architecture Over Expediency

- **No "Quick Fixes":** If a fix violates the architecture, the architecture needs to evolve or the fix needs to be rethought.
- **Predictable Patterns:** Favor boring, proven patterns over "clever" one-liners. If a junior dev can't understand it in 30 seconds, it's too complex.
- **The Rule of Three:** If you copy-paste code twice, abstract it. If you abstract it, ensure the abstraction is flexible enough for a third use case.

### 2. Radical Reliability (The ETF Standard)

Since this project handles financial logic (ETFs), precision is non-negotiable.

- **Fail Loudly:** Never use empty catch blocks. If something fails, it should crash the process or log an error that cannot be ignored.
- **Immutable by Default:** In financial logic, state mutation is the enemy. Use immutable data structures to prevent side-effect bugs.
- **Type Safety is Mandatory:** Use strict typing. If the AI suggests `any` or `unknown` without a massive justification, it has failed.

### 3. Documentation is Code

- **The "Why," not the "How":** Code tells you how; comments should tell you why. Explain the business logic or the edge case that forced a specific implementation.
- **Self-Documenting API:** Function names should be descriptive enough that comments are almost redundant. `calculateRollingVolatility()` is better than `calcVol()`.

---

## The "Considerate Coworker" Protocol

When the AI acts as a coworker, it must follow these behavioral constraints:

- **Contextual Awareness:** Before proposing a change, the AI must analyze how that change ripples through the entire system, not just the local file.
- **Proactive Refactoring:** If you are touching a file to add a feature, and you see "trash" (dead code, messy logic), you are obligated to clean it. *Leave the campsite cleaner than you found it.*
- **The "No-Break" Policy:** Every feature must be accompanied by a test case. If a suggestion removes an existing test or bypasses a safety check, it is a regression.

---

## Tactical Implementation Checklist

Every PR / code generation must pass this mental filter:

| Requirement | Description |
|-------------|-------------|
| **Idempotency** | Can this function run 100 times without changing the result or corrupting data? |
| **Observability** | Is there enough logging to debug this in production without a debugger? |
| **Separation of Concerns** | Does this function do exactly one thing? |
| **Edge Case Resilience** | What happens if the API returns `null`? What if the market is closed? |

---

## Fighting Entropy

Entropy is the natural tendency of a codebase to become messy. We fight it by:

- **Deleting Code:** The most stable code is the code that doesn't exist. Delete unused features ruthlessly.
- **Modularization:** Keep components small. Large files are where bugs hide and developers get lost.
- **Consistency:** Follow the established style guide perfectly. Inconsistency creates cognitive load.
