# Construction Review Checklist

Language-agnostic review questions condensed from the chapter checklists in Steve McConnell's
*Code Complete, 2nd Edition*. Companion to [philosophy.md](philosophy.md): that file explains
*why*; this one is for checking work.

The questions are paraphrased and merged, and language-specific items (C++/Java/VB syntax, pointer
handling, goto rules) are left out. A "no" is a prompt to look closer, not an automatic defect.
Numeric thresholds are the book's rules of thumb.

---

## Design

- Did you try more than one design and pick the best, rather than keep the first that worked?
- Did you try decomposing the system in more than one way, working both top-down and bottom-up?
- Were risky or unfamiliar parts prototyped with the minimum throwaway code needed to answer a specific question?
- Has someone else reviewed the design?
- Is the design developed far enough that the implementation seems obvious?
- Is the design stratified into layers, each coherent on its own?
- Are classes and subsystems designed to interact as little as possible?
- Is the design lean? Is every part strictly necessary?
- Does it use standard techniques and avoid exotic, hard-to-understand elements?
- Overall, does it minimize both essential and accidental complexity?

## Classes and modules

**Abstraction**

- Does the class have one central purpose, and does its name describe it?
- Does the interface present a consistent level of abstraction?
- Is it obvious from the interface how to use the class?
- Can you use it as a black box, without thinking about its implementation?
- Are its services complete enough that callers never need to touch its internal data?
- Has unrelated information been moved out?
- Is the integrity of the interface being preserved as the class is modified?

**Encapsulation**

- Is member accessibility as restricted as possible? Is member data hidden?
- Are implementation details hidden as far as the language allows?
- Does the class avoid assumptions about its users, including subclasses?
- Is it loosely coupled to other classes?

**Inheritance**

- Is inheritance used only for true "is a" relationships, where a subclass can stand in for its parent?
- Are shared interfaces, data, and behavior as high in the tree as possible?
- Are inheritance trees shallow?

**Implementation**

- Does the class have about seven data members or fewer?
- Does it call into other classes only as much as necessary?
- Is all member data initialized on construction?

## Routines

- Is there a sufficient reason for the routine to exist?
- Has everything that would benefit from being its own routine been extracted?
- Is the name a clear verb-plus-object (for a procedure) or a description of the return value (for a function)?
- Does the name describe *everything* the routine does?
- Does the routine do one thing and do it well?
- Are its connections to other routines small, visible, and flexible?
- Is its length determined by its logic, not by an arbitrary limit?

**Parameters**

- Does the parameter list, as a whole, present a consistent abstraction?
- Are parameters in a sensible order, matching similar routines?
- Are there seven or fewer?
- Is every parameter used?
- Are input parameters left unmodified, not reused as working variables?
- Are interface assumptions documented?
- Does a function return a valid value under all circumstances?

## Defensive programming

- Does the routine protect itself from bad input?
- Are assertions used to document assumptions (preconditions, postconditions), and only for conditions that should never occur?
- Is there one project-wide approach to error handling, and does it state whether to favor robustness or correctness?
- Are there barricades that validate data at boundaries, so less code has to deal with errors?
- Are errors made hard to overlook during development?
- Is the amount of defensive code appropriate: neither too little nor too much?

**Exceptions**

- Is there a standard project approach to exceptions?
- Was an alternative to throwing considered? Could the error be handled locally?
- Is each exception at the same level of abstraction as the routine that throws it?
- Does each exception carry the context needed to understand it?
- Are there no empty catch blocks (or is each one justified in a comment)?

**Security**

- Does input validation cover malicious input (injection, overflow), not only accidental bad data?
- Are all error codes checked and all exceptions caught?
- Do error messages avoid revealing information useful to an attacker?

## Variables and data

- Are variables declared close to first use and initialized at declaration?
- Are counters, accumulators, and variables in repeated code reinitialized correctly?
- Does each variable have the smallest possible scope?
- Are references to each variable close together, with a short live time?
- Is every declared variable used?
- Does each variable have exactly one purpose, with no hidden meanings?
- Is binding time a conscious choice between flexibility and added complexity?
- Are related data items grouped into a structure or class rather than passed around loose?
- Is data local or class-scoped unless it truly must be global?
- Is unavoidable global data reached through access routines, and documented?
- Is the code free of "pseudo-global" objects: large grab-bags of data passed to every routine?
- Are named constants or enumerations used in place of magic numbers, magic strings, and makeshift flags?
- Does the code build with all warnings enabled and none reported?

## Naming

- Does the name fully and accurately describe what the thing represents?
- Does it refer to the real-world problem, not the programming-language solution?
- Is it long enough that no one has to puzzle it out?
- Are loop indexes meaningfully named when the loop is nested or longer than a couple of lines?
- Have "temporary" variables been given real names?
- Are booleans named so that their meaning when true is clear?
- Are constants named for what they represent, not for their value?
- Does the naming convention distinguish locals, class members, and globals, and types, constants, and variables?
- Is the convention compatible with the language's standard conventions?
- Are abbreviations avoided, or at least consistent?

**Avoid names that are:** misleading; similar in meaning to another name; different by only one or
two characters; similar in sound; distinguished only by numerals; deliberately misspelled;
in conflict with standard library names; arbitrary.

## Control flow

**Conditionals**

- Is the nominal path through the code clear?
- Does the normal case follow the `if` rather than the `else`?
- Are complicated tests wrapped in well-named boolean functions or variables?
- In chains, are the most common cases first, and are all cases covered?
- Is the action for each case simple, calling another routine if needed?
- Is the default / final `else` used to detect and report unexpected cases?

**Loops**

- Is the right kind of loop used?
- Is the loop entered from the top, with initialization directly before it?
- Does the loop do one thing, as a well-defined routine would?
- Is it short enough to see all at once? If long, has the body been moved into a routine?
- Is nesting three levels or less?
- Is housekeeping grouped at the start or end of the body?
- Is the loop index left alone inside the body, and not used after the loop?
- Is the termination condition obvious, and does the loop end under all conditions?

**General**

- Are boolean expressions stated positively and fully parenthesized?
- Have deeply nested statements been simplified (guard clauses, extracted routines, restructured conditions, tables, polymorphism)?
- Could a lookup table replace a complicated logic chain or inheritance tree?
- If a routine has more than about 10 decision points, is there a good reason not to redesign it?
- Do early returns make the routine more readable, and are they used only where they do?
- Does recursion have a guaranteed stopping point, a bounded depth, and a real advantage over iteration?

## Readability and comments

- Can someone pick up the code and start understanding it immediately?
- Is the code straightforward, without cleverness?
- Is it written in problem-domain terms as far as possible?
- Does the layout show the logical structure?
- Are related statements grouped, and independent groups extracted into routines?

**Comments**

- Do comments explain intent or summarize, rather than repeat the code?
- Do they focus on *why* rather than *how*?
- Has tricky code been rewritten instead of commented?
- Are comments current, clear, and correct?
- Does every comment earn its place?
- Are surprises, workarounds, and undocumented behavior flagged?
- Are units, valid ranges, coded meanings, and input limitations documented on data declarations?
- Is the purpose of each routine stated, plus relevant assumptions, limitations, and side effects?
- Is there a short overview of how the program is organized?

## Testing

- Does each requirement and each design element that applies to the unit have a test?
- Is every line of code exercised by at least one test?
- Are boundaries tested: minimum, maximum, and off-by-one?
- Are compound boundaries tested, where inputs combine into a value too large or too small?
- Is the wrong *kind* of data tested (invalid, too little, too much, uninitialized)?
- Are typical, middle-of-the-road values tested?
- Are minimum and maximum normal configurations tested?
- Is compatibility with old data and old versions of dependencies tested?
- Have errors that occurred frequently in the past been turned into tests?
- Are expected results easy to verify by hand?

## Debugging

**Finding**

- Is the error stabilized: can you reproduce it reliably, in more than one way?
- Is your hypothesis based on all the available data, including negative results?
- Have you narrowed the suspicious region? If stuck, have you widened it?
- Have you checked recently changed code, and code that has had defects before?
- Have you explained the problem to someone else, or taken a break?
- Have you set a time limit on quick-and-dirty attempts before switching to a systematic approach?

**Fixing**

- Do you understand the problem, and the surrounding program, before fixing?
- Have you confirmed the diagnosis?
- Are you fixing the problem and not the symptom?
- Is each change made for a specific reason, one change at a time?
- Have you verified the fix and added a test that exposes the defect?
- Have you looked for similar defects elsewhere?

## Refactoring

**Signals that refactoring is needed**

- Duplicated code.
- A routine that is too long; a loop that is too long or too deeply nested.
- A class with poor cohesion, or an interface with an inconsistent level of abstraction.
- Too many parameters.
- A change requires parallel edits in several classes, hierarchies, or `case` statements.
- Related data used together but not grouped.
- A routine that uses more of another class than its own.
- A primitive type carrying too much meaning.
- A class that does very little; a middleman that does nothing.
- Data passed through a chain of routines that don't use it.
- One class that knows too much about another.
- A poor routine name.
- Public data members; global variables.
- A subclass that uses only a small part of its parent.
- Comments used to explain difficult code.
- Setup code before, or cleanup code after, a routine call.
- Code that "might be needed someday".

**Doing it safely**

- Is the starting point saved?
- Is each refactoring small, and are they done one at a time?
- Is there a written list of intended steps, and a place to park ideas that come up midway?
- Do you retest after each one?
- Are complicated or critical changes reviewed?
- Does the change improve internal quality?
- Is this real refactoring of working code, not a cover for tweaking broken code or for avoiding a needed rewrite?

## Performance

- Have you looked for gains in requirements, design, data structures, algorithms, and I/O before considering code-level tuning?
- Is the program fully correct before tuning begins?
- Were bottlenecks measured before any change?
- Was the effect of each change measured?
- Were changes that didn't help backed out?
- Did you try more than one approach per bottleneck?

## Integration

- Is there a deliberate integration order, coordinated with the order of construction?
- Does the approach make defects easy to localize?
- Are interfaces between components well specified?
- Is the project built frequently (ideally daily), with an automated smoke test on every build?
- Is code checked in frequently, at most a day or two apart?
- Does the smoke test grow with the code?
- Is a broken build rare, and is the build still run under schedule pressure?
