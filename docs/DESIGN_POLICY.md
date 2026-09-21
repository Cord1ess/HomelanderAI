# Software Design & Implementation Policy

**Status:** Binding for all work in this repository. Where this policy and [SPEC.md](SPEC.md) disagree on *how* something is built, this policy wins. SPEC.md remains the authority on *what* gets built.

## Core Principle

**Always choose the simplest solution that correctly solves the problem.**

The goal of this project is to build software that is:

* Simple
* Understandable
* Maintainable
* Reliable
* Easy to debug
* Easy to modify later

Do **not** add complexity just because a more advanced, scalable, abstract, or "proper" solution exists.

> **If a simple solution works, use the simple solution.**

---

## 1. Simplicity Comes First

Before implementing anything, ask:

1. What is the simplest way to solve this?
2. Can this be done with the tools, libraries, and architecture we already have?
3. Do we actually need a new dependency, abstraction, service, class, pattern, or system?
4. Can the solution be implemented with significantly less code?
5. Am I solving a real requirement or a hypothetical future problem?

Prefer:

```text
Simple > Clever
Explicit > Abstract
Existing > New
Local > Distributed
Direct > Indirect
Small > Large
Practical > Theoretical
```

Do not optimize for hypothetical requirements.

---

## 2. No Overengineering

Do **not** introduce:

* Unnecessary design patterns
* Unnecessary abstractions
* Unnecessary interfaces
* Unnecessary classes
* Unnecessary helper functions
* Unnecessary utility layers
* Unnecessary wrappers
* Unnecessary configuration systems
* Unnecessary state management
* Unnecessary APIs
* Unnecessary microservices
* Unnecessary databases
* Unnecessary caching
* Unnecessary queues
* Unnecessary dependency injection
* Unnecessary event systems
* Unnecessary third-party libraries

unless there is a clear, current requirement for them.

For example, do not create:

```text
Controller → Service → Repository → Factory → Adapter
```

when the feature can simply be implemented directly.

Likewise, do not create a generic abstraction for something that is only used once.

---

## 3. Avoid Premature Optimization

Do not optimize code before there is evidence that optimization is necessary.

First make it:

1. Correct
2. Simple
3. Readable
4. Reliable

Only optimize when there is an actual performance problem or a clear requirement.

Do not add caching, memoization, workers, concurrency, batching, virtualization, complex algorithms, or other optimizations simply because they "might be useful later."

---

## 4. Minimize Dependencies

Before adding a package/library, ask:

> "Can this reasonably be implemented using what we already have?"

If yes, prefer the existing tools.

Do not add a dependency for a trivial operation that can be implemented with a small amount of straightforward code.

Every dependency adds:

* Complexity
* Maintenance
* Potential bugs
* Security concerns
* Version conflicts
* Build complexity

Use external libraries when they provide substantial value, not for convenience alone.

---

## 5. Prefer Existing Project Structure

Before creating a new file, component, class, service, hook, utility, or module:

**Look at the existing codebase first.**

Reuse existing:

* Components
* Functions
* Utilities
* Types
* Services
* API patterns
* Styling patterns
* Data structures
* Error handling patterns

Do not create a duplicate implementation when an existing implementation can reasonably be reused.

---

## 6. Keep Code Local When Possible

Prefer keeping related logic together when it improves readability.

Do not split code into multiple files merely to make individual files smaller.

For example, this is often unnecessary:

```text
UserCard.tsx
UserCardHeader.tsx
UserCardAvatar.tsx
UserCardName.tsx
UserCardActions.tsx
```

if the entire component is small and understandable as one file.

**File separation should solve a real organizational problem.**

---

## 7. Avoid Unnecessary Abstraction

Do not abstract code merely because two pieces of code look similar.

Abstract when:

* The same logic is genuinely reused
* The abstraction makes the code easier to understand
* It prevents meaningful duplication
* It represents a clear concept in the application

Do not create:

```text
BaseManager
AbstractManager
GenericManagerFactory
ManagerProvider
```

just because several functions perform related operations.

Simple duplication can sometimes be better than a complicated abstraction.

---

## 8. Do Not Build for Imaginary Future Requirements

Never implement features or architecture based solely on:

> "We might need this later."

Build for requirements that actually exist.

Do not add:

* Multi-tenant architecture when there is one tenant
* Distributed infrastructure when one server is sufficient
* Plugin systems when there are no plugins
* Complex permissions when simple roles are sufficient
* Multiple database layers when one database is sufficient
* Generic configuration systems when a simple configuration is sufficient

Future requirements can be handled when they actually appear.

---

## 9. Use the Simplest Appropriate Architecture

Choose architecture based on the **actual size and requirements of the project**.

Do not use enterprise architecture for a small application.

Do not use microservices when a monolith is sufficient.

Do not use real-time infrastructure when normal HTTP requests are sufficient.

Do not use a database when static/local data is sufficient.

Do not use a state-management library when local/component state is sufficient.

Do not use a complex backend when a simple API is sufficient.

**Architecture should match the problem, not the developer's ambition.**

---

## 10. Keep APIs Simple

Prefer straightforward APIs.

Example:

```ts
getUser(id)
```

is preferable to:

```ts
getUser({
    identifier: id,
    options: {
        includeMetadata: true,
        useCache: false,
        strategy: "default"
    }
})
```

unless those options are actually required.

Avoid configuration objects containing many optional properties when a simple function can solve the problem.

---

## 11. Keep State Management Simple

Use the smallest state scope necessary.

Prefer:

```text
Local state
↓
Parent state
↓
Context
↓
Global state
```

Only move state to a more global system when necessary.

Do not introduce global state simply because it is available.

Avoid storing derived values in state when they can be calculated directly.

---

## 12. Error Handling Should Be Practical

Handle errors that can realistically occur.

Do not create elaborate error-handling frameworks for simple operations.

Prefer clear handling:

```ts
try {
    ...
} catch (error) {
    ...
}
```

over building an entire custom error architecture unless the project genuinely requires one.

Do not silently swallow errors.

Do not add excessive defensive checks for impossible situations unless they protect against a realistic failure.

---

## 13. Comments Should Explain "Why"

Do not write comments that simply restate the code.

Bad:

```ts
// Increment counter
counter++;
```

Good:

```ts
// Keep the counter in sync with the server because the response
// does not include the updated value.
counter++;
```

If code requires extensive comments to explain what it does, consider whether the implementation itself can be simplified.

---

## 14. Do Not Change Unrelated Code

When implementing a feature or fixing a bug:

**Change only what is necessary.**

Do not:

* Refactor unrelated files
* Rename unrelated variables
* Replace working libraries
* Rewrite existing architecture
* Reformat the entire project
* "Clean up" unrelated code

unless specifically requested.

Small changes are easier to review, test, and debug.

---

## 15. Preserve Existing Working Behavior

Never replace working code with a more complicated solution without a clear reason.

Before modifying existing behavior, understand why the current implementation exists.

When possible:

```text
Existing working solution
        ↓
Small targeted modification
```

instead of:

```text
Existing working solution
        ↓
Complete rewrite
        ↓
New architecture
        ↓
New dependencies
```

---

## 16. Solve the Actual Problem

Do not blindly implement the user's requested technical approach if a significantly simpler approach solves the actual requirement.

For example:

If the requirement is:

> "The user needs to refresh the displayed data."

Do not automatically build WebSockets.

A normal API request may be sufficient.

If the requirement is:

> "Two components need to share a small amount of state."

Do not automatically introduce Redux or another global state system.

Use the simplest appropriate solution.

---

## 17. Before Adding Complexity, Justify It

Whenever an implementation introduces significant complexity, first identify the concrete reason.

Ask:

> **What specific requirement makes this complexity necessary?**

If there is no strong answer, choose the simpler implementation.

Complexity should be **earned by requirements**.

---

## 18. Prefer Readability

Code should be understandable by another developer quickly.

Prefer:

```ts
const total = price * quantity;
```

over clever one-liners that require mental decoding.

Prefer clear names over short names.

Prefer straightforward control flow over clever tricks.

The best code is often code that looks boring.

---

## 19. Don't Over-Engineer for Scale

Do not design for millions of users if the current application has no such requirement.

Do not introduce distributed systems, sharding, queues, complex caching, load balancing, or horizontal scaling solely because they are technically possible.

Build the smallest architecture that can comfortably handle the **known requirements**.

If the requirements change, the architecture can evolve.

---

## 20. Implementation Process

For every feature, follow this process:

### Step 1 — Understand

Identify exactly what needs to happen.

### Step 2 — Inspect

Check the existing project structure and implementation patterns.

### Step 3 — Find the simplest solution

Think of at least one straightforward implementation before considering advanced approaches.

### Step 4 — Reuse

Reuse existing code and dependencies whenever reasonable.

### Step 5 — Implement minimally

Make the smallest change that completely satisfies the requirement.

### Step 6 — Verify

Test the actual behavior.

### Step 7 — Stop

**Do not keep improving or abstracting the implementation after the requirement is satisfied unless there is a concrete benefit.**

---

## Colour

The brand is a **hue**, not a hex list: yellow-green at **68.5°**, where all
three reference colours sit (`#3D4127` 69.2°, `#636B2F` 68.0°, `#D4DE95` 68.2°).
Hue and saturation carry the identity. Lightness is the free variable, because
lightness is what contrast is made of.

Every value in `apps/web/src/theme.ts` and the `--neo-*` block of `index.css`
was therefore **solved, not picked**: given a surface and a contrast target,
find the lightness in our hue that just clears it. The numbers look arbitrary
because each one is the point where a requirement is met. Nudging one by eye
silently breaks the guarantee it was chosen for — re-solve instead.

**The ramp is split by scheme.** `clinical[0..5]` are solved against the dark
card `#1E1F16`; `clinical[6..9]` against the light page `#F8F9F3`. A single
shade cannot serve both: the lightness that reads on near-black is the one that
vanishes on near-white. Hence `primaryShade: { light: 6, dark: 3 }`. Using a
light-half step on a dark surface is the easiest mistake to make here — it was
made once already, putting a 3.46:1 label on the active nav item.

Key steps, with what they are for:

| Step | Hex | On | Use |
|---|---|---|---|
| `clinical[2]` | `#CED98C` | 11.03:1 dark | Active nav, key figures |
| `clinical[3]` | `#A0B13E` | 7.01:1 dark | **Primary on dark** |
| `clinical[4]` | `#7F8C34` | 4.52:1 dark | Text floor on dark |
| `clinical[5]` | `#646E2B` | 3.01:1 dark | Boundaries, large text only |
| `clinical[6]` | `#6D7826` | 4.54:1 light | **Primary on light** |
| `clinical[8]` | `#3D4127` | 10.00:1 light | Structural dark olive |

**Filled buttons on dark take dark ink.** The dark primary is a *light* olive,
so Mantine's default white label would be 2.37:1. The theme overrides
`[data-variant="filled"]` to `dark-7`, which is 8.17:1.

**Risk tiers are not brand colours.** `TierBadge` stays teal / yellow / red /
gray. It is a traffic light an underwriter reads at a glance, and the brand is
yellow-green: an olive "low" beside a yellow "moderate" would be nearly the same
hue on the one chip where confusion is most expensive. Status colour stays
independent of the accent so a rebrand cannot make two risk levels look alike.

---

# Claude's Decision Rule

When choosing between two implementations, prefer the one that:

1. Uses fewer moving parts
2. Uses less code
3. Uses fewer dependencies
4. Is easier to understand
5. Is easier to debug
6. Is easier to modify
7. Reuses more existing code
8. Introduces fewer abstractions
9. Has fewer failure points
10. Still completely satisfies the requirements

If both solutions satisfy the requirements, **choose the simpler one.**

---

# Anti-Overengineering Rule

Before introducing any new architectural concept, ask:

> **Can I solve this correctly without introducing it?**

If the answer is yes, **do not introduce it.**

Before adding a dependency:

> **Can I reasonably do this without the dependency?**

If yes, avoid the dependency.

Before creating an abstraction:

> **Will this abstraction solve an actual current problem?**

If no, do not create it.

Before refactoring:

> **Is this refactor necessary for the current task?**

If no, don't do it.

---

# Final Rule

## Make it work. Make it clear. Keep it simple.

Do not demonstrate complexity.

Do not optimize for hypothetical requirements.

Do not build infrastructure that the project does not need.

Do not introduce abstractions just because they are considered "best practice."

**The simplest correct solution is the preferred solution.**
