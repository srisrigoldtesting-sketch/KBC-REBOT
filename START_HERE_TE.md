# KBC REBOT — మీ Windows laptopలో ప్రారంభించండి

1. ZIPని పూర్తిగా **Extract All** చేయండి. చిన్న folder path ఎంచుకోండి, ఉదాహరణకు `C:\KBC-REBOT`.
2. **INSTALL.cmd**ని double-click చేయండి. Python/dependencies install చేసి local tests నడుపుతుంది. Internet అవసరం. WinGet అందుబాటులో లేకపోతే official Python download సూచన చూపిస్తుంది.
3. తెరుచుకున్న settings windowలో మీ API ID, API hash, **కొత్త bot token**, Admin ID, private channel ID నమోదు చేసి **Save settings** నొక్కండి. ఒక్క token మాత్రమే paste చేయండి; `< >` పెట్టవద్దు.
4. కొత్త Premium session కావాలంటే API ID/hash save చేసి window మూసేయండి. **GENERATE_SESSION.cmd** తెరవండి. మీ Telegram phone number, login code, two-step password అడిగితే ఆ laptop windowలోనే నమోదు చేయండి. Session నేరుగా private settingsలో save అవుతుంది.
5. Telegramలో private broadcast channelలో bot, Premium account రెండింటినీ adminsగా చేర్చండి. రెండింటికీ **Post Messages**, **Delete Messages** permissions ఇవ్వండి. Protected content ఆపండి. ఆ channel `-100...` IDని settingsలో పెట్టండి.
6. **CHECK.cmd** నడపండి. ఏ setting సరిచేయాలో చూపిస్తే **CONFIGURE.cmd**లో సరిచేసి మళ్లీ CHECK చేయండి.
7. **START.cmd** తెరిచి ఉంచండి. Bot running అని వచ్చిన తర్వాత Telegramలో `/start` పంపండి. చిన్న document పంపి, దానికి replyగా `/rename New Name.pdf` పంపండి. అది పనిచేసిన తర్వాత పెద్ద file పరీక్షించండి.

**MongoDB అవసరం లేదు:** DATABASE_URL ఖాళీగా ఉంచితే laptopలో local database వాడుతుంది. FORCE_SUB_CHANNEL కూడా optional; bot usernameని channel స్థానంలో పెట్టవద్దు.

**మీ laptop ఆన్‌లో, charger మరియు internetతో ఉండాలి.** START నడిచేంతవరకు idle sleepని తాత్కాలికంగా ఆపుతుంది; lid మూసేయడం/manual sleep/shutdown చేస్తే bot ఆగుతుంది. Ctrl+Cతో ఆపండి. Laptop restart తర్వాత START మళ్లీ తెరవండి.

ఇది hosting bill లేని local setup. Telegram Premium, internet, electricity ఖర్చులు వేరు. 4GBకి active Premium user account అవసరం. గరిష్ఠ పరిమితి 4000 MiB; కనీసం 5 GiB ఖాళీ disk అవసరం, 10 GiB ఉంచడం మంచిది.

ముందు chatలో పెట్టిన token/session/passwordలను తిరిగి వాడవద్దు. కొత్తవి laptopలోనే నమోదు చేయండి. `.env`ని GitHubకి, ZIPలోకి లేదా chatకి పంపవద్దు. GitHubలో పెట్టిన variables మీ laptopకి ఆటోమేటిక్‌గా రావు.

CHECKకి ముందు పాత START window మూసేయండి. ఒక userకి ఒక job మాత్రమే. `/status`తో చూడవచ్చు; `/cancel`తో ఆపవచ్చు. Power/internet సమస్య తర్వాత jobని మళ్లీ పంపాలి.
