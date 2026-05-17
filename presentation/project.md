# Introduction
- Before we begin *Goal of Demo*: Showcase standard workflow for the sales employee
- Most of the inquiries are received by mail => Decided to build a Plugin for easy integration

# Start
- Employee receives an email pricing inquiry, wants to create a pricing offer
- Use the pdf inquiry example provided by ElringKlinger + wrote a simple Mail Body Text
- Simply clicking on the quotation button, opens up the sidebar 
- Shows running pipeline, currently extracting content (Mail Text + Attachments) and sending them to the LLM
- Preview of the received PDF + Text as well as the extracted Positions
- Human in the loop now needs to check if extracted information is correct
- Cross referencing with PDF Viewer => Allows to find errors
- Discount is currently global, can be extended to be article based
- Adding / Deleting positions is possible



- Preiswarnung(en) aus Kalkulation => Always present if no_match, fuzzy or semantic
- Certificate Position => No discount


# Questions
## Matching:
- **Exact Match** on article number
- **Fuzzy Match** on article number, external library rapidfuzz. 
  Uses Levenstein Distance to compare strings
- **Semantic Match**: Activated if no exact and no fuzzy match on article number. Fuzzy matching on name of product and material

## Highlighting:
Fuzzy Matching of extracted position on to original document. 
=> Simulates which parts of the original document the llm used to extract the position.
=> Does not prove the LLM truly looked at exactly that area internally. 
=> Highlights the source evidence that supports the extracted information.

## Fast Path
- Tries Determenistic extraction before LLM . 
- Extraction of article number based on determenistic automata which is build using a python package (pyahocorasick). Automata looks like prefix tree.
- Quantity is matched using regex 
- Fires rarely but allows very fast extraction

## Data
- Grouped Overview_Offers.xlsx File by article number and selected important columns
- Base price is calculated as base_price = median(price_per_piece)

## LLM
- LLM calling with retries (standard 3 times)
- LLM returns JSON Object => Used to match on database
- Hallucinations are minimized by a single request to the LLM:
- Position extraction is done via LLM
- Mapping to Articles from database is done deterministically (via exact article number, fuzzy matching etc.)

## Testing
Frontend:
- Playwright used to test 
Backend:
- Parsing of Mails (Loading of CSV, XLSX etc.)
- Matching (Exact Match, Fuzzy Match, No Match etc.)
- Review- / Approval Workflow (Approval State Machine)





Infrastructure:
FastAPI Backend, React Review-UI and Outlook Add-in

Supports PDF, Excel, CSV and pure Text
PDF, Image -> Image
CSV, Excel -> Markdown

