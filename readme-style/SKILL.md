---
name: readme-style
description: Captures William Entriken's prose voice from repositories in ~/Developer, including recurring pedantic precision, inconsistent mechanics, inspired directness, and template-grade reproducibility patterns for technical writing and commit text.
---

# Prose voice and style

## Scope

Use this skill when writing README content, technical notes, commit messages, release docs or issue comments.

## Avoid weasles and hedging

Words are written once and read many times. Readers rely on writers to be knowledgeable, confident and generous with their time and words. Writers consider the readers' position and estimate the problems they are solving.

Case study 1: A README starts with "install using `bundle`". This is underspecified and will lead to errors. Setting up Ruby is hard, and especially picking the right version. Instead, specify which Ruby is needed and provide concrete direction of how to set it up.

## When to use title case

Use title case only for the name of a published product (a standalone article is not a product), something that is a proper noun (check Wikipedia for adjudication), and for the action text of a button (until Apple HIG removes that requirement).

## Temporal consistency and "love notes"

If a file currently says "use a hammer" and an LLM is directed to update that, it may change it to "use a screwdriver (updated from hammer because you asked me to)". This is an error because the note "updated from hammer because you asked me to" is intended for the person talking with the LLM, and the file is directed for a different audience.

Another example: A project includes an internal function A and has just cutover to use a new function B, deprecating the first. This is an error because function A is now dead code (remember, it is only accessible internally?) Leaving this dead code in the project could only be considered a love note because it is completely unuseful for the rest of the world who is reading this implementation.

Avoid love notes.

## Non-odvious things deserve explanation

Ambitious people with different levels of ability work on project together. If specific guidence is in one place and application of it is non-obvious in another place, it is likely that the senior person will intuitively comply, and the junior person will revert them because they are both fixing the problem at their own level of understanding. This is an unproductive commit war.

The solution is that guidence should show the gatcha (e.g. "scripts use `yarn node` instead of `node` because of PnP, using just `node` will fail, specifically with markdownlint-cli"), and the implementation should add a comment (JSON uses `"--":` for comments) saying why `yarn node` is used.

P.S. If you need to change an implementation which is specifically cited to a best practice, you need to measure if changing the implementation necessitates an update to the best practice.

## Best practices deserve citation

The problem you are working on has already been discussed by many people, arguing both ways. These people can be a continual source of inspiration for how we work. 

We should seek other's published notes on our approach, especially from people that are active in our field of study. This is especially helpful when we may question our own work in the future. For example, setting up iOS build testing is hard, undocumented and requires updates. We often follow Alamofire's approach, and we must cite exactly what we took, how, why and any delta we maintain.

## Be thoughtful with API shape

Adding configurable options is easy. Removing them is divine.

Thoughtfully consider if fail-fast is appropriate, considering the consumer's situation. Fail-fast is most transparent and is easiest to reason about. New configuration options can multiply the surface area and add support for unneeded/unrequested use cases. Practice displine by talking through the consumer position before supporting new surface area.