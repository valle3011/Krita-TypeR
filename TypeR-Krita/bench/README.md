# Judging the shaper against finished pages

The shaper's score is a dozen weighted judgements, and until now the only
way to know whether a change to them helped was to look at a few bubbles
and form an opinion. Finished chapters are better than an opinion: they
are what a letterer actually chose.

Two scripts, both read-only. Neither touches the chapters.

```bash
# 1. pull the lettering out of the .kra pages
python bench/ts_extract.py blocks.json "…/Ch. 95/TS" "…/Ch. 94/TS" …

# 2. ask where the letterer's own line breaking comes out in the ranking
python bench/ts_bench.py blocks.json
```

`ts_extract` reads each page's zip: a TypeR text layer is a `shapelayer`
whose `content.svg` holds one `<text>` with a `<tspan>` per line and the
family and pixel size in its style. That is everything the shaper is
judged on - the words, how they were broken, the font, and the size a
person settled on - plus the gap between the tspans, which gives the
line height that was really used.

`ts_bench` gives the shaper the same words at the same size and asks
where the person's own arrangement lands in the ranking.

## What it can and cannot say

**The bubble is not in the .kra.** Only the block is, so the box has to
be the block with the padding added back. The person's shape therefore
starts with the box's own proportions, which flatters it.

So a pass proves little. **A miss proves a lot**: among arrangements of
the same words at the same size, in a box the person's own block fits,
the scorer preferred something else. Read the misses, not the
percentage.

The percentage is still the right thing to watch *across a change*,
because the flattery is the same on both sides of it.

## What it measured

1238 dialogue blocks (two lines or more, three words or more) from
**eleven** chapters of *Houkago no Idol ni wa Himitsu ga aru* (85-95),
2367 text layers in all.

Eighteen chapters were read; seven of them gave nothing. Before TypeR
named its layers they are Krita's own `Vector Layer 1`, and the
extractor only takes layers whose name says TypeR. Those chapters are
reachable with `ANY=1`, at the risk of picking up lettering that was
not done with the plugin - see the held-out set below, which is exactly
that.

| | first | top three | offered at all |
|---|---|---|---|
| before | 36.1 % | 81.3 % | 97.3 % |
| the starved-bubble fix | 37.9 % | 83.8 % | 97.6 % |
| with `_SENSE_LEAN` | **45.9 %** | **86.6 %** | **97.6 %** |

Two things came out of it that no amount of looking at bubbles would
have.

**The first attempt at the starved-bubble fix was worse than doing
nothing** - 79.4 % on the top three against 81.0 % - because it
softened the line-count charge from zero and so weakened it for the
candidates near the ideal, which is nearly all of them. That is how the
knee came to be shaped the way it is.

**The shaper wanted one line too few.** Of the blocks where the
letterer's own shape missed the top three, 86 % were a disagreement
about the *number* of lines, and in 134 of those the shaper's pick had
exactly one line fewer. A half-line lean towards more, shorter lines
(`_SENSE_LEAN`) is worth eight points of exact agreement.

That second number deserves its caveat: a box built from the letterer's
own block is as tall as their line count, so the measurement flatters
counts near theirs. What says the lean is real anyway is the shape of
the sweep - it peaks at +0.75 and collapses by +1.5. A purely circular
measurement would just keep climbing.

## The held-out set

Chapters 78-84 are lettered from before TypeR named its layers, so they
were invisible to the extractor while `_SENSE_LEAN` was being chosen.
They are a clean out-of-sample test - 859 blocks that had no say in the
number:

| | first | top three |
|---|---|---|
| without the lean | 34.6 % | 74.2 % |
| with it | **40.2 %** | **77.1 %** |

The gain survives on pages that played no part in producing it, which
is the strongest thing that can be said for a constant like this.

Their absolute agreement is lower (40 % against 46 %) and the shaper
fails to offer the letterer's shape at all 11.4 % of the time against
2.4 %. These are older chapters, in places lettered by somebody else -
so they are the right thing to validate against and the wrong thing to
tune on.
