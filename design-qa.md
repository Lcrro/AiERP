# Material Marketplace Design QA

## Scope

- Reference: Aesop Shop All page supplied by the user.
- Implementation: `http://127.0.0.1:8788/material-marketplace`.
- Comparison artifact: `.runtime/design-qa/material-marketplace/comparison-desktop.png`.
- Desktop comparison viewport: 1440 x 1000 CSS pixels.
- Mobile verification viewport: 417 x 844 CSS pixels after the in-app browser's viewport constraints were applied.
- Final implementation screenshot after review updates: .runtime/design-qa/material-marketplace/implementation-final.png.

## Visual comparison

- Layout: retained the reference's thin top navigation, broad cream canvas, large editorial heading, left refinement column and three-column catalogue rhythm. Added a persistent request-list column because purchase-request assembly is the core Nexterp task.
- Typography: editorial serif headings are paired with the existing Nexterp sans-serif UI language. Weight and hierarchy remain restrained and close to the reference.
- Colour and borders: matched the warm off-white ground, near-black copy and fine rules; used Nexterp teal only for active or actionable states.
- Cards: the catalogue has no verified product photography, so cards use honest typographic catalogue plates rather than invented product photos. Product names, codes, attributes and units all come from the approved material catalogue.
- Category filter: the left filter now exposes the full material path as an expandable tree, from GPC segment through the internal standard type at the leaf; selecting any node filters all descendant materials.
- Copy: all retail language was adapted to internal procurement. Price and inventory are explicitly marked as unavailable until ERPNext readback.

## Interaction verification

- Search and facet filtering update the catalogue and result count.
- Add, quantity edit, remove and clear actions update the persistent request list.
- Project, employee, required date and purpose are included in the handoff.
- Handoff opens the employee workbench and pre-fills a request that explicitly requires a frozen preview and confirmation; it does not write automatically.
- Mobile filters start collapsed, the request list opens as a drawer, and no horizontal overflow is present.
- Browser console verification reported no errors or warnings.

## Follow-up

- Add real, reviewed material photography later when the catalogue owns dependable images. Until then, the current typographic treatment avoids misleading users.

final result: passed

---

# Material Marketplace Variant Selector Pilot QA

## Evidence

- Source visual truth: `C:/Users/SGJ/AppData/Local/Temp/codex-clipboard-2a5b5c02-dad2-48b4-8693-5b79da9cabf0.png` (震坤行规格选型参考，1717 × 990 px).
- Browser-rendered implementation: `C:/Users/SGJ/AppData/Local/Temp/nexterp-material-variant-pilot/02-rebar-selector-final.png` (Nexterp 钢筋规格选择器，1078 × 983 px).
- Combined comparison: `C:/Users/SGJ/AppData/Local/Temp/nexterp-material-variant-pilot/comparison-reference-implementation.png`.
- CSS viewport: 1078 × 983; device scale factor 1. Source and implementation were normalized to a common 990 px content height in the combined image. The source is a full retail product-detail layout, while the implementation intentionally compares only its specification-selection interaction pattern.
- State: searched for “抗震热轧带肋钢筋”, opened the standard-type card, selected `HRB400E` and `10 mm`, resolved concrete SKU `100081630102001`.

## Findings

- No actionable P0/P1/P2 issue remains.
- Fonts and typography: the implementation retains Nexterp's editorial serif heading and restrained sans-serif controls instead of copying the source brand typography; option hierarchy and resolved-SKU emphasis remain clear.
- Spacing and layout rhythm: the modal keeps the selectable attributes, fixed attribute, resolved SKU and quantity action in one continuous reading path. The narrower internal-workflow density is intentional.
- Colors and visual tokens: Nexterp cream, near-black and teal tokens replace the source's red retail palette; selected, disabled and resolved states remain distinguishable.
- Image quality and assets: the selector does not invent product photography. This is intentional because the current catalogue has no reviewed steel-rebar imagery and the interaction does not depend on a product photo.
- Copy and content: wording is procurement-specific, states that only existing SKUs are shown, and exposes the exact selected material code before adding it to the request.

## Comparison history

1. Initial implementation exposed one grouped card and resolved valid combinations, but “1 item” and “26” facet counts used different unexplained units (P2 clarity issue).
2. Fixed the result summary to distinguish standard types/materials from concrete SKUs and added `SKU` suffixes to classification counts.
3. Added quantity preservation while changing specification selections.
4. Re-captured the resolved state; no P0/P1/P2 difference remained. Focused-region evidence was not separately required because the implementation screenshot is already a close, readable capture of the selector and resolved-SKU region.

## Primary interactions tested

- Search collapses 26 rebar SKUs into one standard-type card.
- Opening the card loads existing variants only.
- Selecting brand and nominal diameter resolves exactly one concrete SKU.
- Invalid combinations become disabled.
- Quantity survives option changes.
- Adding the result places the concrete SKU, not the group code, in the request list.
- Browser console errors: none.

final result: passed
