## ADDED Requirements

### Requirement: A value object's textual form is its value

Exactly seven vocabulary value objects carry a single value, and each SHALL render as text as exactly that value: the product identifier, the SKU, the ASIN, the marketplace identifier, the metric identifier, the discipline and the severity. Rendering one SHALL yield the value it carries and nothing else: no type name, no field name, no punctuation around it. Constructing the same kind of value object from a rendered one SHALL yield a value equal to the original.

Code SHALL carry a value object into text by its value. No message, prompt, log line, persisted record or control payload SHALL be composed from a rendering of the *object* — the object's debugging representation belongs to a debugger, a traceback and a diagnostic, and naming a value to a person or to a machine is not that.

This is stated for the whole vocabulary, and not only where it has already gone wrong, because the same mistake has now been made four times in three modules and each time silently. `subcategory-advisor` states it for one handler's prompt, after a marketplace identifier reached an advisor as a rendering of the object holding it; a launch thread's anchor and a stuck-step report have each since carried a product identifier the same way, and a decision control has carried one in whichever form its composer happened to receive. Scoping the rule to one capability is what left the other three unprotected.

The fault is not cosmetic wherever the text is written once and not rewritten. A launch's thread anchor is established once and never re-created, so a product identifier rendered as an object becomes that thread's permanent heading; a control payload is parsed rather than read, so a value in the wrong form is not merely ugly but unresolvable.

Every other vocabulary value has **no single value** to render as, and is outside the first paragraph: a lifecycle stage carrying a phase or a posture carries more than one, a stage such as `Development` or `Retired` carries none, and an access scope is either a distinct unrestricted construction or a set. Inventing a textual form for any of them would be this requirement choosing a format rather than stating one. The prohibition in the second paragraph still binds every one of them: such a value is named to a person by its parts, never by a rendering of the object.

#### Scenario: Rendering a single-valued vocabulary object yields its value

- **WHEN** a product identifier, SKU, ASIN, marketplace identifier, metric identifier, discipline or severity is rendered as text
- **THEN** the result is exactly the value it carries, with no type name or field name around it

#### Scenario: A rendered value object round-trips

- **WHEN** a single-valued vocabulary object is rendered as text and a value object of the same kind is constructed from the result
- **THEN** it compares equal to the original

#### Scenario: A value with no single value is not rendered as an object

- **WHEN** a lifecycle stage or an access scope is named to a person
- **THEN** it is named by its parts, and no rendering of the object is composed into the text

#### Scenario: A debugging representation is still available

- **WHEN** a value object is inspected for a diagnostic rather than rendered into text a person reads or a machine parses
- **THEN** a representation naming the type and its value is still available, and remains distinct from the textual form
