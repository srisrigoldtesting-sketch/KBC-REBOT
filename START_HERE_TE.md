# KBC REBOT — Premium లేకుండా ప్రారంభించండి

**ఈ కొత్త versionలో STRING_SESSION అవసరం లేదు.** సాధారణ bot modeలో phone number/OTP ఇవ్వాల్సిన అవసరం కూడా లేదు. ఒక్క file‌గా 2000 MiB వరకు rename చేసి పంపుతుంది. పెద్ద files‌ను భాగాలుగా పంపి, laptopలో మళ్లీ కలపవచ్చు.

1. పాత **START** windowని Ctrl+Cతో ఆపండి. పాత **CONFIGURE** window కూడా మూసేయండి.
2. కొత్త ZIPని పూర్తిగా **Extract All** చేయండి. ఉదాహరణకు `C:\KBC-REBOT` వంటి చిన్న folder path వాడండి.
3. **INSTALL.cmd** తెరవండి. మీ పాత `.env` settings వాడాలంటే దాన్ని కొత్త folderకి laptopలోనే copy చేయవచ్చు; chat/GitHubకి పంపవద్దు.
4. Settingsలో **Transfer mode = bot** ఎంచుకోండి. API_ID, API_HASH, BOT_TOKEN, ADMIN_ID నమోదు చేయండి. **STRING_SESSION**, **STAGING_CHAT_ID** ఖాళీగా ఉంచండి. Bot modeలో ఈ రెండింటిలో పాత తప్పు values ఉన్నా వాటిని ఉపయోగించదు.
5. MongoDB అవసరం లేకపోతే DATABASE_URL ఖాళీగా ఉంచండి. Channel features అవసరం లేకపోతే FORCE_SUB_CHANNEL, LOG_CHANNEL_ID కూడా ఖాళీగా ఉంచండి. Save చేసి window మూసేయండి.
6. **CHECK.cmd** నడపండి. Checks పాస్ అయితే **START.cmd** తెరిచి ఉంచండి.
7. Telegramలో `/start` పంపి, చిన్న document పంపండి. దానికి replyగా `/rename New Name.pdf` పంపండి.

## పెద్ద file ఇప్పటికే Telegramలో ఉంటే

Forward చేయడానికి అనుమతి ఉన్న fileని botకి forward చేయండి. దానికి replyగా `/splitrename New Name.mp4` పంపండి. 4000 MiB వరకు inputని తీసుకుని, ఒక్కో భాగం 2000 MiB మించకుండా పంపుతుంది. చివరలో `.kbc-parts.json` file కూడా పంపుతుంది.

**అన్ని భాగాలు మరియు JSON fileని ఒకే folderలో download చేయండి. పేర్లు మార్చవద్దు. JOIN_PARTS.cmd తెరిచి JSON fileని ఎంచుకోండి.** అది భాగాలను తనిఖీ చేసి పూర్తి renamed fileని తయారు చేస్తుంది. భాగాలు విడిగా videoలా play కావు. మధ్యలో job ఆగితే అసంపూర్ణ భాగాలను తొలగించి మళ్లీ ప్రయత్నించండి; వేర్వేరు attempts భాగాలు కలపవద్దు.

## పెద్ద file మీ laptopలో మాత్రమే ఉంటే

Premium లేకుండా ఆ 4GB fileని Telegramకి ఒక్క file‌గా upload చేయలేరు. **SPLIT_LOCAL.cmd** తెరిచి fileని ఎంచుకుని చివరకు కావలసిన కొత్త పేరు ఇవ్వండి. కొత్త folderలో parts మరియు JSON సిద్ధమవుతాయి. వాటిని Telegramలో వేర్వేరుగా పంపండి. అందుకున్నవారు JOIN_PARTSతో పూర్తి fileని తిరిగి పొందవచ్చు. మీ original file అలాగే ఉంటుంది.

ఇది ఒకే 4GB Telegram upload కాదు: చిన్న భాగాలుగా పంపి, తరువాత కలిపే విధానం. `4GB` అనే advertised tierకి ఈ library పరిమితి 4000 MiB; ఖచ్చితమైన 4 GiB file దీని కంటే పెద్దది.

## Session గురించి

**GENERATE_SESSION.cmd ఇప్పుడు optional.** సాధారణ Telegram accountతో కూడా session తయారు చేయవచ్చు. Session తయారు చేసినంత మాత్రాన Premium రాదు. ప్రత్యేకంగా user mode ఎంచుకుంటేనే session మరియు private staging channel అవసరం. మీకు ప్రస్తుతం **bot mode** సరిపోతుంది.

Laptop charger/internetతో ఆన్‌లో ఉండాలి; START window తెరిచి ఉంచండి. సాధారణ renamingకి సుమారు 3 GiB, పెద్ద split jobsకి సుమారు 7 GiB ఖాళీ అవసరం; 10 GiB ఉంచడం మంచిది. Telegramలో bot స్పందిస్తుందో చిన్న fileతో ముందుగా పరీక్షించండి. మీ laptop/accountతో live transfer ఇక్కడి నుంచి పరీక్షించలేదు.

Token, API hash, session, OTP లేదా passwordsని chat/GitHubకి పంపవద్దు. ముందుగా బయటపడిన token/sessionలను తిరిగి వాడవద్దు.
