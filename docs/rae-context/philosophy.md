# Philosophy of Software Construction

A synthesis of the ideas in Steve McConnell's *Code Complete, 2nd Edition* (Microsoft Press, 2004).
This is a distillation in my own words, not an excerpt. Section references (e.g. §5.2) point back to
the book for the full argument.

---

## The one idea

**Software's primary technical imperative is managing complexity.** (§5.2, §34.1)

No one can hold a whole program in their head. Almost every practice in the book is a way of
shrinking how much you must think about at one time:

- **Essential complexity** comes from the problem itself. Divide it so only a small piece is in view at once.
- **Accidental complexity** comes from our tools and choices. Stop it from spreading.

The working test for any design: *while immersed in one part, can I safely ignore the rest?*
If not, the design isn't doing its job.

Everything below is this idea applied at a different scale.

---

## Nine themes

These are the book's own closing themes (Ch. 34), restated.

1. **Conquer complexity.** Subsystems, interfaces, short routines, clear names, shallow nesting,
   no global data, and conventions all exist for this one purpose.
2. **Pick your process.** How you work shapes what you produce. Quality has to be built in from the
   first step; it cannot be tested in at the end. Doing things in the wrong order (coding before the
   design is understood, optimizing before the code works) is a process error.
3. **Write for people first, computers second.** Code is read far more often than it is written.
   Favor read-time convenience over write-time convenience, even for code "only you" will see,
   because habits don't switch on and off and private code tends to become public.
4. **Program *into* your language, not *in* it.** Decide what you want to express, then find a way
   to express it with the tools at hand. Don't let the language's features set the limits of your
   thinking; cover its weaknesses with conventions.
5. **Use conventions to focus attention.** Many decisions are arbitrary. Making them once, the same
   way every time, frees attention for decisions that matter. A convention followed consistently
   beats a "better" one followed sometimes. Too many conventions is its own failure.
6. **Program in terms of the problem domain.** Top-level code should read like a description of the
   problem, not of files, stacks, and indexes. Build layers so the upper ones speak the user's
   vocabulary and the implementation details sit below.
7. **Watch for falling rocks.** Treat discomfort as data. "Tricky" code, names that are hard to
   choose, comments that are hard to write, classes that are hard to test, error-prone modules,
   repeated similar edits: each is a warning that the design or the process needs another look.
   *If it's hard, it's probably wrong. Make it simpler.*
8. **Iterate, repeatedly.** Requirements, design, estimates, code, and tuning all improve with
   repeated attempts. The first solution that works is rarely the best. Iterate early, where it is
   cheap, not late, where it is expensive.
9. **Keep religion out of software.** Development is heuristic, not algorithmic. No single
   methodology, style, or rule fits every problem. Keep a full toolbox, choose per problem, and
   settle disagreements with experiments and measurement instead of belief.

---

## Before you build

- **Preparation is risk reduction.** The goal of upstream work is to remove the biggest risks before
  they become expensive. (Ch. 3)
- **Defects cost more the longer they live.** A requirements mistake found after construction costs
  many times what it costs to fix early (the book cites 20x to 100x). Find problems close to where
  they were introduced.
- **Know what kind of project you're on.** How much to plan up front versus iterate depends on the
  project: how stable the requirements are, how critical the system is, how large the team. Neither
  "plan everything" nor "plan nothing" is a default.
- **Three prerequisites:** a clear problem definition (or you solve the wrong problem), requirements
  (or you miss details of the right problem), and architecture (or you solve it the wrong way).
- **Make the key construction decisions deliberately:** language, conventions, and which practices
  to use. Establish conventions before coding; retrofitting them is nearly impossible. (Ch. 4)
- **Metaphors are thinking tools.** Software as *construction* suggests planning, staged work, and
  scale-dependent rigor. Practices as an *intellectual toolbox* suggests choosing the right tool per
  job. (Ch. 2)

---

## Design

Design is a **wicked, sloppy, heuristic** process: you often have to partly solve the problem to
understand it, you make mistakes on the way, and it involves tradeoffs and priorities rather than
proofs. (Ch. 5)

**What a good design looks like:** minimal complexity, ease of maintenance, loose coupling,
extensibility, reusability, high fan-in, low-to-medium fan-out, portability, leanness (no extra
parts), and stratification (each level makes sense on its own).

**The heuristics that matter most:**

- **Hide secrets (information hiding).** The single most useful question in design is
  *"What should I hide?"* Hide complexity so you don't have to think about it, and hide sources of
  change so their effects stay local.
- **Form consistent abstractions.** An interface should let you forget what is behind it.
- **Encapsulate.** Abstraction says you *may* ignore the details; encapsulation says you *can't*
  depend on them.
- **Identify areas likely to change** and isolate them: business rules, hardware dependencies,
  I/O, nonstandard language features, difficult design areas, status variables, data-size limits.
- **Keep coupling loose.** Small, visible, flexible connections between modules.
- **Aim for strong cohesion.** Each unit does one thing.
- **Find real-world objects; look for common patterns; consider brute force; draw a diagram.**
- **Inherit only when it truly simplifies.** Inheritance adds complexity; prefer containment unless
  the relationship is a real "is a".

**Practices:** iterate; divide and conquer; work top-down and bottom-up as each stalls; prototype to
answer specific questions and throw the prototype away; get someone else to look at the design.
Don't stop at the first design that works.

---

## Classes and routines

**Classes** (Ch. 6)

- A class is an abstract data type: data plus the operations that make sense on it.
- The interface should present one consistent level of abstraction and hide something: a design
  decision, a system interface, an implementation detail.
- Protect the abstraction when the class is modified; interfaces erode one convenient addition at a time.
- Don't make assumptions about a class's users, and don't read its implementation to learn how to use it.
- Classes are the primary tool for managing complexity. Don't let one grow into a whole program.

**Routines** (Ch. 7)

- The best reason to create a routine is to make the program easier to think about. Reducing
  duplication, hiding sequences, and isolating change follow from that. Even a one-line operation
  can deserve its own routine.
- Aim for functional cohesion: one routine, one job.
- **The name is a quality signal.** If a routine is hard to name clearly, or its accurate name is
  awkward, the routine is probably poorly designed.
- Keep parameter lists short and consistent; pass what preserves the interface's abstraction.
- Use a function only when its main purpose is to return the value its name describes.

**The Pseudocode Programming Process** (Ch. 9): design the routine in plain-language statements of
intent, review and iterate on that, then fill in code beneath each statement. The pseudocode becomes
the comments. Mistakes are caught when they are cheapest to fix.

---

## Defensive programming

(Ch. 8)

- Protect the program from bad input; "garbage in, garbage out" is not acceptable for production code.
- **Assertions** document and check conditions that should *never* occur. **Error handling** deals
  with conditions you *expect* might occur. Don't confuse them.
- Decide, as a design matter, how errors are handled, and favor **correctness** or **robustness**
  deliberately, depending on the system.
- **Barricades:** validate data at the boundary so code inside can assume it is clean.
- Use exceptions with discipline; undisciplined, they are as hard to follow as gotos.
- **Offensive programming:** development builds can be much harsher than production builds. Fail
  loudly and early in development so problems can't be overlooked.
- Treat input as hostile, not just mistaken: check for malicious data, check every error return,
  and keep error messages from helping an attacker.
- Don't overdo it. Defensive code is also code that must be read, tested, and maintained.

---

## Data

(Ch. 10–13)

- **Names carry the design.** A good name fully and accurately describes what the thing represents,
  in problem-domain terms ("what", not "how"). Vague names that could serve several purposes are bad names.
- **One variable, one purpose.** No hidden meanings, no reuse for something unrelated.
- **Minimize scope, span, and live time.** Declare close to first use, initialize at declaration,
  keep references to a variable close together.
- **Avoid global data**, not only because it is dangerous but because better options exist. If you
  must have it, reach it through access routines.
- **Bind as late as the flexibility is worth, and no later.** Late binding buys flexibility at the
  cost of complexity.
- Replace magic numbers and strings with named constants and enumerations.
- Define your own types where they make intent clearer and changes easier.
- Wrap error-prone mechanisms (pointers, raw structures) behind routines or classes.

---

## Control flow

(Ch. 14–19)

- **Make order dependencies obvious** through names, parameters, and structure. Where order doesn't
  matter, keep related statements together.
- **Put the normal path first** and make it easy to see; handle errors without burying the nominal case.
- **Keep loops simple:** one purpose, clear entry and exit, housekeeping in one place, indexes that
  are well named and used for one thing.
- **Tame deep nesting.** More than about three levels is a warning. Use guard clauses, extract
  routines, or restructure.
- **Simplify boolean expressions:** name them, wrap them in boolean functions, state them positively.
- **Table-driven methods:** when logic chains or inheritance trees get confusing, ask whether a
  lookup table would be simpler.
- Unusual structures (multiple returns, recursion, goto) are tools for specific cases. Use them
  where they make code clearer, never by habit.
- Complexity can be measured roughly by counting decision points in a routine; past about ten,
  consider simplifying.

---

## Quality

(Ch. 20–23)

- **The General Principle of Software Quality: improving quality reduces development cost.** The
  best way to improve both productivity and quality is to cut rework, whether it comes from
  requirements changes, design changes, or debugging.
- **No single technique catches everything.** Reviews, testing, and other methods find *different*
  kinds of defects. Combine them.
- **Collaboration is a quality technique.** Reviews, inspections, and pair programming find a large
  share of defects, often more efficiently than testing, and spread knowledge.
- **Testing shows the presence of defects; it does not create quality.** It tells you how the
  software is broken, not how to make it more usable, readable, or extensible.
- **Developer testing:** test each unit as you build it; writing tests first costs the same effort
  and shortens the find-fix cycle; cover boundaries, bad data, and data flow; automate for regression.
- **Errors cluster.** A few routines hold most of the defects. Find them, redesign them, rewrite them.
- **Quality goals conflict.** Decide explicitly which matter for this project and say so.

**Debugging** is a last resort made systematic:

1. Stabilize the error (make it reproducible).
2. Locate the source: gather data, form a hypothesis, decide how to prove or disprove it, do so, repeat.
3. Fix the defect.
4. Test the fix.
5. Look for similar errors elsewhere.

When fixing: understand the problem and the program before changing anything, fix the problem and
not the symptom, make one change at a time, and add a test that exposes the defect. Guessing and
random changes leave the program worse. Assume the error is yours. Turn compiler warnings to the
strictest level and fix them.

---

## Change

(Ch. 24–26)

- **The Cardinal Rule of Software Evolution: change should improve internal quality.** Software
  either gets better or gets worse each time it is touched.
- **Refactor on purpose.** Learn the smells (duplication, long routines, deep nesting, poor
  cohesion, long parameter lists, changes that ripple). Refactor in small steps, one at a time,
  with tests, and keep refactoring separate from behavior changes.
- Refactoring means changing *working* code without changing its behavior. Tweaking broken code
  until it runs is hacking, not refactoring.
- Some code doesn't need small changes; it needs to be thrown out and rewritten. Don't refactor to
  avoid that.

**Performance**

- Performance is one quality attribute among several and usually not the most important.
- Architecture, design, and algorithm choices matter far more than code-level tuning.
- **Measure first.** Programs spend most of their time in a small part of the code, and you won't
  guess which part. Intuition about what is fast is frequently wrong.
- **Measure again afterward.** Results vary by language, compiler, and environment; many
  "optimizations" make things slower.
- Write clean, modifiable code first. That is the best preparation for tuning the parts that need it.

---

## Scale and teams

(Ch. 27–30)

- **Size changes everything.** As projects grow, communication paths multiply, defect density
  rises, productivity per person falls, and construction becomes a smaller share of the work.
  Practices that are optional on small projects become necessary.
- **Methodology is mostly a communication aid.** Judge it by how well it helps people coordinate.
  Scaling a light process up works better than scaling a heavy one down; aim for "right-weight".
- **Integrate incrementally.** Add and test one piece at a time so new problems have an obvious
  source. Build and smoke-test daily.
- **Configuration management and change control** make programmers' lives easier when done properly.
- **Estimate with data, by several methods, and re-estimate** as the project becomes better understood.
- **Measure.** An imperfect measurement beats none.
- **Programmers are people.** Individual and team variation is large; environment, autonomy, and
  respect matter.
- **Invest in tools,** and build small ones of your own when none exist.

---

## Craft

**Layout** (Ch. 31): the purpose of formatting is to show the logical structure of the code
accurately and consistently. Appearance is secondary. Style disputes should be argued with explicit
criteria, not taste.

**Comments and self-documenting code** (Ch. 32)

- Good code is its own best documentation. If code needs heavy commenting to be understood, improve
  the code first.
- Comments should say what the code cannot say about itself: **intent and summary**, the *why*.
  Don't repeat the code.
- Keep information close to the thing it describes so it stays current.
- Use a comment style that is cheap to maintain.

**Personal character** (Ch. 33)

The building material of software is human intellect, and the primary tool is you. No employer can
make you a good programmer; that is a matter of character, and character matters more than raw
intelligence.

- **Humility.** Nobody is smart enough to hold a real program in their head. The best programmers
  accept this and compensate: they decompose, keep routines short, follow conventions, work in
  problem-domain terms, and ask for review. How you focus your intelligence matters more than how
  much you have.
- **Curiosity.** The technical environment turns over every few years, so learning has to be
  deliberate. Pay attention to your own development process. Experiment with small programs before
  relying on something you don't understand, and make mistakes quickly and learn from them. Read
  documentation, books, and other people's code, good and bad. Seek criticism of your own code.
  Lean toward analysis before action; most programmers err on the side of acting too soon.
- **Intellectual honesty.** Don't pretend to expertise you lack. Admit mistakes quickly. Understand
  a warning instead of suppressing it. Understand the program instead of running it "to see if it
  works"; that temptation is a sign you started coding too early. Be able to state how certain you
  are; if it's always 100 percent, that's a warning. Report status realistically. **Estimates are
  not negotiable:** you can refine an estimate or renegotiate scope, but not bargain over how long
  the work takes, and underestimating to get a project approved takes a decision away from the
  people whose job it is to make it.
- **Communication and cooperation.** Programming is communicating with another programmer first and
  the computer second. Write for the person who will modify the code.
- **Creativity and discipline.** Conventions don't stifle creativity; they make it possible at
  scale. Settle the noncritical matters by convention and spend creativity where it counts.
- **Laziness, of the right kinds.** Putting off an unpleasant task is the bad kind. Doing it
  immediately to get it out of the way is "enlightened laziness". Writing a tool so you never do it
  again is "long-term laziness", the most productive kind, provided the tool actually saves time.
  Conversely, looking busy is not progress: the most important work is thinking.

**Traits that matter less than they seem**

- **Persistence.** Usually it is just stubbornness. When stuck, set a time limit, then try another
  approach, redesign, or come back later. Avoiding a problem beats fighting it.
- **Experience.** Knowledge changes fast, old habits can be worse than none, and people draw wrong
  conclusions from their own history. Ten years can be one year repeated ten times. Experience only
  counts if you reflect on it and keep learning.
- **Gonzo programming.** All-night heroics produce defects that take weeks to repair. Excitement is
  no substitute for competence.

**Habits.** Most of what a programmer does is done without conscious thought, so habits decide the
outcome. Learn things the right way the first time, while you are still paying attention. To lose a
bad habit, replace it with a good one rather than trying to simply stop.

---

## Quick heuristics

- What should this hide?
- Can I ignore the rest of the system while working here?
- Would a maintainer understand this without asking me?
- Is the name easy to choose and accurate? If not, revisit the design.
- Is this "clever"? Then make it simple instead.
- Does this variable, routine, or class do exactly one thing?
- Is this the first design I thought of? What are two others?
- Am I doing things in the right order?
- Have I measured, or am I guessing?
- Am I fixing the cause or the symptom?
- Does this change leave the code better than I found it?
- Is this a rule I'm following out of belief, or because it fits this problem?
