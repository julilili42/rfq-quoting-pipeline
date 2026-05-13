**Introduction**
- Before we begin *Goal of Demo*: Showcase standard workflow for the sales employee
- Prototype consists of Review Website + Outlook Plugin
- Start our demo in outlook, and work ourselves towards the review website
- Most of the inquiries are received by mail => Decided to build a Plugin for easy integration

**Start**
- Employee receives an email pricing inquiry, wants to create a pricing offer
- Use the pdf inquiry example provided by ElringKlinger + wrote a simple Mail Body Text
- Simply clicking on the quotation button, opens up the sidebar 
- Shows running pipeline, currently extracting content (Mail Text + Attachments) and sending them to the LLM
- Preview of the received PDF + Text as well as the extracted Positions
- Human in the loop now needs to check if extracted information is correct
- Cross referencing with PDF Viewer => Allows to find errors
- Discount is currently global, can be extended to be article based
- Adding / Deleting positions is possible



Infrastructure:
FastAPI Backend, React Review-UI and Outlook Add-in

Supports PDF, Excel, CSV and pure Text
PDF, Image -> Image
CSV, Excel -> Markdown


Data:
Grouped Overview_Offers.xlsx File by article number and selected important columns


LLM:
- LLM calling with retries (standard 3 times)
- LLM returns JSON Object => Used to match on database
Hallucinations are minimized by a single request to the LLM:
- Position extraction is done via LLM
- Mapping to Articles from database is done deterministically (via exact article number, fuzzy matching etc.)




Testing:
Frontend:
- Playwright used to test 
Backend:
- Parsing of Mails (Loading of CSV, XLSX etc.)
- Matching (Exact Match, Fuzzy Match, No Match etc.)
- Review- / Approval Workflow (Approval State Machine)



What does the key account manager want to hear?

Target Audience: Key account manager
IT as well 

IT costs should be mentioned

Friday: Reutlingen
Saturday: Tübingen


SCRUM als anhang
