## ADDED Requirements

### Requirement: A handler's waiting does not stop the process

A handler SHALL reach a model, a service or a database such that **waiting for the answer yields control to whatever else the invoking process is running**. While a handler's dependency has not yet answered, other work scheduled on the loop the handler was invoked on SHALL continue to progress.

Where a dependency offers an asynchronous entry point, the handler SHALL use it. Where a dependency offers **only** a blocking entry point, the handler SHALL await that call off the invoking thread.

**A framework moving a handler's synchronous code onto a thread on its behalf does not satisfy the first of those.** Where a library accepts synchronous work and runs it in a thread pool when reached asynchronously, a handler that hands it blocking code has not used the dependency's asynchronous entry point — it has relied on an accommodation the library makes for code that could not. Other work on the loop does progress, so such a handler passes the observable above while being the shape this requirement exists to end: the choice is invisible at the call site, it costs a thread per invocation for work that is only waiting, and removing the accommodation later reintroduces the block silently. Where an asynchronous entry point exists, using it is the obligation, and the observable is not the whole of the test.

A thread offload for a dependency that genuinely offers no asynchronous entry point is not an evasion but the correct accommodation, and satisfies this requirement fully. It SHOULD state at the call site why no asynchronous entry point was available — a review obligation rather than one carrying an observable of its own, because nothing at runtime can distinguish an offload chosen deliberately from one nobody examined, and the reason is what a reviewer needs in order to tell the difference.

How a handler waits SHALL NOT change what it produces. A handler converted from a blocking call to an awaited one SHALL produce the same outcome, the same result text and the same finding for the same answers from its dependency.

**This is not a property the handler type can carry.** A handler is registered as returning an awaitable, and a coroutine that never yields satisfies that exactly — `async def` describes what a function returns, not whether the work inside it ever gives the loop back. Nor is it a property a linter checks: a rule that knows a particular HTTP client's blocking call site does not know a third-party library's synchronous entry point. The obligation is therefore stated here rather than delegated to a tool.

Most of it is carried by each handler's own tests, which is why the first clause is expressed as an observable rather than as a prohibition on a syntax. Two clauses are not, and are named as such rather than left to look like clauses nobody bothered to test: which entry point a handler reached is a fact about the source that no runtime observation distinguishes, and why an offload was chosen is a fact only its author knows. Those are held at review. A requirement whose parts are checked in different places is more useful than one narrowed to the part a test can reach.

**Why it matters is a property of the deployment, not a preference.** The recurring work that invokes handlers runs on one loop inside a process that is also doing other things — its own job bookkeeping, any concurrently deferred job, any overlapping pass. The pass invokes handlers one at a time and awaits each, which is what makes one handler's latency cost the pass its own time. A handler that blocks instead makes that latency cost the whole process, for as long as its dependency takes to answer, which for a model call is unbounded.

**This is not a licence to run handlers concurrently.** The pass's serial walk over launches and steps is unchanged, and this requirement governs what a handler owes the process that invokes it, not how the pass invokes one — the pass already awaits each handler correctly.

#### Scenario: A handler's waiting leaves the invoking loop free

- **WHEN** a handler is invoked on a loop that also has other work scheduled, and the handler's dependency has not yet answered
- **THEN** that other work progresses before the handler returns, and the handler then returns its resolution as it otherwise would

#### Scenario: A dependency offering only a blocking call is awaited off the invoking thread

- **WHEN** a handler's only way to reach a dependency is a blocking call, and the handler awaits it off the invoking thread
- **THEN** other work scheduled on the invoking loop still progresses while the handler waits, and the handler satisfies this requirement

#### Scenario: A framework's thread offload does not stand in for a dependency's asynchronous entry point

- **WHEN** a handler hands synchronous code to a library that offers an asynchronous entry point and that runs such code in a thread pool on the handler's behalf
- **THEN** the handler does not satisfy this requirement, notwithstanding that other work on the invoking loop progresses

#### Scenario: How a handler waits does not change what it produces

- **WHEN** a handler that reached its dependency by a blocking call is changed to await the same dependency, and the dependency answers exactly as before
- **THEN** the handler produces the same outcome, the same result text and the same finding as it did before the change
