# Concepts

Four ideas explain every design decision in this repository. None of them is complicated;
all four are easy to get backwards, and getting one backwards makes the whole tool look
arbitrary.

## [Two billing modes with opposite goals](billing-modes.md)

The same routing question — "which model should run this?" — has two different correct
answers depending on how the tokens are paid for. Pay-per-token means optimize dollars, so
the cheapest sufficient model wins. A subscription means the marginal dollar is zero and
the scarce resource is your rate-limit window, so downgrading buys nothing and the dial you
actually turn is effort. The mode attaches to the *question*, not to you. Read this one
first if you are on a plan.

## [The one constraint that shapes everything](the-one-constraint.md)

Nothing can programmatically switch your main session's model — not a hook, not a skill,
not a settings write. Only you, typing the switch command. Two things *are* programmable,
and the entire architect/execute design is built on the first of them. This is why the
router prints a command for you to paste instead of just doing it.

## [Architect, execute, measure](architect-execute-measure.md)

The frontier model does the expensive thinking once and writes it down as a kit — plans,
task briefs with model pins, verification loops. Cheaper models then execute the kit,
escalating one task at a time when a specific step gets stuck. Then measurement closes the
loop and turns "the cheap model was probably fine" into evidence.

## [Effort and context](effort-and-context.md)

Model choice is the coarse dial. Two finer ones matter just as much: how hard the chosen
model thinks, and how much you are carrying in the window when it thinks. Both are
measurable, and on a subscription they are the levers that actually move burn.

## Where these show up

Every skill in the [skills reference](../skills/index.md) implements some corner of these
four. The [workflows](../workflows/index.md) apply them to a task in front of you. The
[deep dives](../deep-dives/index.md) are the long-form versions with the full mechanics —
these pages distil and route; they do not replace them.
