"""Hand-built lexicons for the shortlist analysis.

Everything here is deliberately simple, auditable and reproducible: no model
calls, no external services. Each pattern is a case-insensitive regex applied
to the 420-char excerpts. Precision was checked against a 40-row random sample
(see REPORT.md, "Validation").
"""

# ---------------------------------------------------------------- topic coding
# Multi-label. Ordered by how the report presents them.
TOPICS = {
    "geopolitics_conflict": r"\b(war|invasion|nato|nuclear|missile|sanctions?|ceasefire|"
    r"genocide|military|troops|occupation|annex|armed conflict|proxy war|militia|"
    r"hezbollah|hamas|gaza|ukraine|russia|israel|palestin|iran|taiwan|south china sea|"
    r"regime change|airstrike|drone strike|coup|terroris\w*|isis|taliban)\b",
    "elections_voting": r"\b(election|elections|electoral|voter|voters|voting|ballot|"
    r"poll|polls|polling|campaign trail|primary|primaries|referend\w*|turnout|"
    r"constituenc\w*|swing state|midterm\w*|by-election|gerrymander\w*|electoral college)\b",
    "parties_ideology": r"\b(party|parties|democrat\w*|republican\w*|conservative\w*|liberal\w*|"
    r"left-wing|right-wing|far-right|far right|far-left|populism|populist|socialis\w*|"
    r"communis\w*|fascis\w*|nationalis\w*|neoliberal\w*|ideolog\w*|labour party|tory|"
    r"tories|gop|maga|progressive\w*|libertarian\w*|centrist|extremis\w*)\b",
    "political_figures": r"\b(trump|biden|harris|obama|modi|putin|xi jinping|erbakan|"
    r"le pen|macron|scholz|merz|starmer|farage|milei|bolsonaro|lula|netanyahu|khamenei|"
    r"kim jong|zelensk\w*|orban|sanders|desantis|vance|rubio|erdogan|imran khan|"
    r"president|prime minister|chancellor|senator|congressm\w*|governor|mayor|cabinet|"
    r"politician|political leader|head of state|king|monarch|dictator)\b",
    "institutions_constitution": r"\b(constitution\w*|federalis\w*|separation of powers|"
    r"supreme court|judiciary|judicial review|parliament\w*|senate|congress|electoral system|"
    r"electoral college|bill of rights|amendment|executive order|impeach\w*|checks and balances|"
    r"referendum|devolution|autonom\w*|sovereignty|rule of law|due process|filibuster|"
    r"first amendment|second amendment|electoral commission|centralis\w*|centraliz\w*)\b",
    "public_policy": r"\b(policy|policies|healthcare|health care|medicare|medicaid|"
    r"affordable care act|obamacare|tax(es|ation)?|budget|deficit|spending|subsid\w*|"
    r"welfare|social security|pension\w*|education|school|housing|rent|zoning|"
    r"climate|energy|emissions|environment|infrastructure|transport|drug policy|"
    r"gun control|firearm|abortion|health insurance|minimum wage|inflation|tariff\w*|"
    r"trade deal|national debt|austerity|privatis\w*|privatiz\w*|national health service|nhs)\b",
    "immigration": r"\b(immigra\w*|migrant\w*|asylum|refugee\w*|border|deport\w*|"
    r"visa|residence permit|naturalis\w*|naturaliz\w*|undocumented|illegal alien|"
    r"schengen|diaspora|expat\w*|citizenship)\b",
    "political_theory": r"\b(democracy|democratic|authoritarian\w*|totalitarian\w*|"
    r"legitimacy|tyranny|despot\w*|liberalism|social contract|justice|equality|freedom|"
    r"liberty|rights|tolerance|pluralism|oligarch\w*|theocracy|anarch\w*|civic|"
    r"public sphere|censorship|free speech|propaganda|political philosophy|"
    r"state power|power corrupts|consent of the governed)\b",
    "political_history": r"\b(world war|wwi|wwii|ww2|cold war|soviet|ussr|holocaust|"
    r"hitler|nazi|stalin\w*|mussolini|fascist italy|colonial\w*|decoloni\w*|"
    r"empire|ottoman|roman empire|qing|dynasty|revolution\w*|independence|"
    r"civil war|apartheid|segregation|civil rights|manhattan project|"
    r"nuremberg|treaty of|versailles|coup d|assassinat\w*|jfk|watergate|"
    r"1989|tiananmen|mccarthy\w*|new deal|great depression)\b",
    "media_info": r"\b(news|headline\w*|journalis\w*|media|press|propaganda|"
    r"disinformation|misinformation|fake news|fact.check\w*|narrative|framing|"
    r"social media|twitter|facebook|tiktok|algorithms?|censorship|debate|"
    r"rhetoric|speech|editorial|op-ed|polling average)\b",
    "civic_practical": r"\b(how (do|can|should) i (vote|register)|register to vote|"
    r"voter registration|absentee|mail-in|polling station|polling place|"
    r"apply for|application|form|document\w*|deadline|filing|permit|license|"
    r"tax return|deduction|social security number|residence permit|"
    r"benefits|eligibility|bureaucra\w*|ministry|municipal\w*|town hall)\b",
    "creative_roleplay": r"\b(write (a|an|the) (story|novel|chapter|speech|dialogue|scene|"
    r"poem|letter|essay|script)|story|novel|fiction|screenplay|roleplay|role-play|"
    r"imagine|scenario|alternate history|what if|character|narrator|protagonist|"
    r"dialogue|monologue|satire|parody|hypothetical)\b",
    "business_tech": r"\b(code|python|javascript|coding|api|database|software|app|"
    r"startup|business plan|market|marketing|revenue|invest\w*|stock|portfolio|"
    r"crypto|blockchain|ai model|llm|machine learning|data analysis|dashboard|"
    r"supply chain|sourcing|logistics|hr|resume|interview|job)\b",
    "other_personal": r"\b(relationship|girlfriend|boyfriend|wife|husband|family|"
    r"health|doctor|therapy|anxiety|depression|sleep|diet|fitness|travel|"
    r"recipe|motivation|habit|study|exam|university|admission|career|"
    r"lonely|friendship|parenting|child|baby|insurance|zus)\b",
}

# Prompt intent / genre. Also multi-label, first match wins for reporting.
INTENTS = {
    "factual_lookup": r"^(who|what|when|where|which|how many|how much|list|tell me about|"
    r"give me info|define|explain|describe|is |are |does |do |did |can |could )",
    "opinion_or_argument": r"\b(do you (think|agree)|don'?t you think|would you say|"
    r"is it (true|fair|justified|right|wrong|bad|good)|should|ought|"
    r"what do you think|your opinion|agree or disagree|argue|convince|"
    r"isn'?t it|right\?|best|worst|overrated|underrated)\b",
    "prediction_or_scenario": r"\b(will|would|could|might|going to|predict\w*|forecast\w*|"
    r"expected outcome|what if|what happens if|chances|probability|likely|scenario|"
    r"future of|by 20\d\d|in 20\d\d)\b",
    "creative_writing": r"\b(write (a|an|the)|story|novel|chapter|poem|speech|"
    r"script|dialogue|scene|satire|parody|roleplay|role-play|imagine|compose|"
    r"draft|generate (a|an))\b",
    "howto_or_advice": r"\b(how (do|can|should) i|how to|steps|guide|help me|advice|"
    r"explain (to me )?how|what should i|need to|process|procedure|"
    r"prepare|plan)\b",
    "comparison_eval": r"\b(compare|versus|vs\.?|difference between|better than|"
    r"which is (better|worse|more)|rank|top \d+|list of|pros and cons)\b",
    "data_or_code": r"\b(visuali[sz]e|chart|graph|plot|dataset|csv|json|code|"
    r"python|javascript|sql|calculate|compute|statistic\w*|table of|"
    r"regression|correlat\w*|rate|percentage|over the past)\b",
    "rewrite_or_edit": r"\b(rewrite|translate|proofread|improve (this|the)|"
    r"summar\w+|paraphrase|edit|revise|make it (shorter|longer|better)|"
    r"fix (this|the)|correct (this|my)|format)\b",
}

# ------------------------------------------------------------------- features
# Applied to the 420-char answer excerpts. Structural markers show up early, so
# truncation costs little for these; length is NOT measured (see REPORT caveats).
STRUCTURE = {
    # NOTE: the checked-in excerpts have had newlines normalised to spaces by the
    # CSV export, so Markdown structure is measured with patterns that survive
    # that: a leading heading, bold runs, inline list markers, pipe tables.
    "lead_heading": r"^\s*#{1,4}\s",
    "bold": r"\*\*[^*]{2,80}\*\*",
    "bullet_list": r"(?:^|\s)[-*\u2022]\s+(?=[A-Z0-9\*\u2018\u201c])",
    "numbered_list": r"(?:^|\s)\d{1,2}\.\s+(?=[A-Z\*\u2018\u201c])",
    "table": r"\|[^|]{1,40}\|[^|]{1,40}\|",
    "emoji": r"[\U0001F300-\U0001FAFF\u2700-\u27BF]",
    "url": r"https?://|www\.",
    "citation_cue": r"\[\d+\]|according to|source:|sources:|as reported by|"
    r"\bper the\b|data from|a (?:20\d\d )?(?:study|report|survey) (?:by|from|found)|"
    r"(?:census|polls?|gallup|pew)\b",
}

EPISTEMIC = {
    "hedge": r"\b(it depends|however|that said|on the other hand|generally|"
    r"largely|typically|in many cases|not necessarily|nuanc\w*|complex|"
    r"varies|can vary|broadly|arguably|somewhat|roughly|approximately|"
    r"reportedly|allegedly|estimates?)\b",
    "both_sides": r"\b(critics|supporters|proponents|opponents|advocates|"
    r"conservatives|liberals|the left|the right|some argue|others argue|"
    r"on both sides|both sides|two views|competing|alternatively)\b",
    "uncertainty_admission": r"\b(i (don'?t|do not) (have|know)|not sure|"
    r"cannot verify|can'?t verify|unclear|disputed|contested|"
    r"estimates vary|no official|as of my knowledge|knowledge cutoff|"
    r"training data|may have changed|unverified|i (?:may|lack) )\b",
    "refusal": r"\b(i can'?t (help|assist|provide|discuss|answer|write)|"
    r"i cannot (help|assist|provide|discuss|answer|write)|"
    r"i'?m (not able|unable) to|i won'?t|as an ai|"
    r"i must (decline|emphasize)|not (allowed|permitted) to|"
    r"i (?:should|must) (?:note|emphasize) that i)\b",
    "disclaimer": r"\b(this is not (legal|financial|medical) advice|consult a|"
    r"important to (note|remember)|please note|keep in mind|"
    r"i am an ai|as a language model|for educational purposes|"
    r"it'?s (?:important|worth) (?:to note|noting))\b",
    "empathy": r"\b(i understand|i'?m sorry|sounds (like|difficult)|"
    r"that'?s (a )?(great|good|tough|fair|sharp|excellent|fascinating)|"
    r"great question|you'?re right|good point|it'?s (completely )?normal|"
    r"i appreciate|thank you for|congratulations)\b",
    "direct_answer": r"^(yes|no|the short answer|in short|short answer|"
    r"the answer is|it'?s|there (is|are))\b",
    "question_to_user": r"\?[\s\u201d')\]]*$",
    "first_person": r"\b(I|my|me)\b",
    "second_person": r"\b(you|your|you'?re)\b",
    "numbers_dates": r"\b\d{1,3}(,\d{3})+|\b\d+(?:\.\d+)?\s?%|\b(1[5-9]\d{2}|20[0-2]\d)\b|"
    r"\$\s?\d|\b\d+\s?(?:million|billion|thousand)\b",
    "named_institution": r"\b(congress|parliament|supreme court|senate|united nations|nato|eu|"
    r"european commission|imf|world bank|who|opec|fbi|cia|pentagon|"
    r"white house|kremlin|ministry|electoral commission|house of representatives)\b",
    "causal_explanation": r"\b(because|due to|as a result|led to|which led|"
    r"resulted in|driven by|so that|therefore|hence)\b",
    "example": r"\b(for example|for instance|e\.g\.|such as|consider)\b",
    "comparison": r"\b(compared (?:to|with)|whereas|in contrast|unlike|"
    r"on the other hand|versus|both)\b",
    "counterargument": r"\b(critics|skeptics|opponents|however|that said|"
    r"while some|others (?:argue|contend)|the counterargument|on the other hand)\b",
    "conclusion": r"\b(in short|overall|in conclusion|bottom line|to summarize|"
    r"in summary|the takeaway|ultimately)\b",
    "recommendation": r"\b(should|recommend|suggest|propose|the best (?:way|approach)|"
    r"a better (?:way|approach)|i'?d advise)\b",
    "caveat": r"\b(caveat|limitation|note that|caveats|with the caveat|"
    r"important caveat|subject to|depending on)\b",
    "moral_language": r"\b(genocide|atrocit\w*|crime against|unjust|evil|brutal\w*|"
    r"oppress\w*|violat\w*|suffering|victims?|massacre|killed|deaths?|"
    r"human rights|dignity)\b",
    "alarm_language": r"\b(threat|danger\w*|risk|collapse|crisis|catastroph\w*|"
    r"escalat\w*|authoritarian|surveillance|erosion|undermin\w*|"
    r"corrupt\w*|rigged|stolen|fraud|conspiracy|backslid\w*)\b",
}

# Organized interests (the literal "interest groups" reading of the brief).
INTEREST_GROUPS = {
    "unions_labor": r"\b(trade union|labor union|labour union|union(s)? (member|boss|"
    r"leader|density)|afl-cio|teamsters|syndicat\w*|collective bargaining|"
    r"minimum wage|gig worker)\b",
    "business_lobby": r"\b(chamber of commerce|business lobby|corporate lobby\w*|"
    r"lobby\w*|special interest\w*|trade association|dark money|super pac|"
    r"pac\b|citizens united|campaign finance|donor class|oligarch\w*|"
    r"k Street|revolving door|regulatory capture)\b",
    "guns": r"\b(nra|national rifle|gun lobby|gun control|gun rights|firearm|"
    r"second amendment)\b",
    "pharma_health": r"\b(big pharma|pharmaceutical (industry|compan\w*)|"
    r"insurance industry|drug pricing|opioid\w*|hospital lobby|ama\b)\b",
    "fossil_energy": r"\b(big oil|oil (industry|compan\w*)|fossil fuel lobby|"
    r"coal industry|exxon|opec|gas lobby|energy lobby)\b",
    "tech_platforms": r"\b(big tech|silicon valley|google|meta platforms|facebook|"
    r"amazon|microsoft|apple|antitrust|monopol\w*|platform regulation|"
    r"section 230|content moderation|algorithmic)\b",
    "finance": r"\b(wall street|big bank\w*|banking lobby|hedge fund\w*|"
    r"private equity|financial sector|lobby\w* bank|too big to fail)\b",
    "religious": r"\b(evangelical\w*|christian right|catholic church|church lobby|"
    r"islamist\w*|cleric\w*|opus dei|religious right|theocracy|sharia)\b",
    "media_owners": r"\b(murdoch|news corp|fox news|msnbc|media conglomerate|"
    r"media ownership|press baron|silvio berlusconi)\b",
    "ethnic_foreign_lobbies": r"\b(aipac|israel lobby|j street|saudi lobby|"
    r"qatar lobby|turkish lobby|diaspora lobby|foreign agent|fara\b|"
    r"kremlin-backed|ccp influence|united front)\b",
    "ngos_thinktanks": r"\b(ngo|ngos|think tank|advocacy group|foundation|"
    r"soros|open society|heritage foundation|brookings|rand corporation|"
    r"civil society organization)\b",
}

# "Sensitive / contested history" probes, useful for the compliance audit.
SENSITIVE = {
    "tiananmen": r"(tiananmen|天安门|天安門|六四|1989年6月4日|june 4(,| )? ?1989|"
    r"june 4|六月四|4 czerwca|masakr\w* na placu)",
    "taiwan_status": r"(taiwan|台湾|台灣)",
    "xinjiang_uyghur": r"(xinjiang|uyghur|uyghurs|维吾尔|再教育营|genocide.{0,40}china)",
    "tibet": r"(tibet|西藏|dalai lama)",
    "xi_leadership": r"(xi jinping|习近平|習近平|winnie the pooh)",
    "holocaust": r"(holocaust|auschwitz|shoah|大屠杀|final solution|gas chamber)",
    "armenian_genocide": r"(armenian genocide|1915)",
    "nanking": r"(nanjing massacre|nanking massacre|rape of nanking)",
    "holodomor": r"(holodomor)",
    "srebrenica": r"(srebrenica)",
}
