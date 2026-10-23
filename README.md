# KINK 1500 Metallica Lettermonitor — volledig gratis op GitHub

**Voor de KINK-actie 19 t/m 30 oktober 2026.** Deze versie vereist **geen eigen server, NAS, Docker, AI-API-sleutel of creditcard**. De code is een hobbyproject, onafhankelijk van KINK of Metallica.

> Belangrijk: dit is **best-effort**, niet een continue of gegarandeerde recorder. GitHub Actions kan geplande runs vertragen of overslaan. Het radiostation, de afspeellijst en de stream kunnen bovendien veranderen. We geven alleen **onbevestigde** lettervoorstellen; verifieer zelf je letters.


## Aanpassing 23 oktober — langere clips en vaker controleren

- Een opname bij de start van Metallica is nu maximaal circa **7 minuten**:
  maximaal 4 minuten vóór het geregistreerde begintijdstip en tot 3 minuten
  erna. De feitelijke opname kan korter zijn wanneer GitHub te laat begon
  of minder audio beschikbaar is. Het bestaande fragment kan niet achteraf
  worden verlengd.
- GitHub Actions kan volgens de officiële documentatie slechts **eens
  per 5 minuten** worden ingepland, en die starts kunnen vertragen.
  Om tussendoor vaker naar Metallica te zoeken controleert de runner
  gedurende maximaal 3 minuten **iedere 45 seconden** de afspeellijst.
  Er zijn normaal vier controles per geplande run; als een echte opname
  start, stopt de extra polling en rondt de recorder eerst zijn werk af.
- Het dashboard krijgt pas na de GitHub-run nieuwe gepubliceerde
  gegevens. De polling is geen garantie op ononderbroken opname;
  een oude Android-telefoon kan als zelfstandige recorder betrouwbaarder zijn.

## Actuele status en gratis pushmeldingen

**Dashboard:** https://gingerodiablo.github.io/kink-lettermonitor/

- Het dashboard toont zowel de laatst opgeslagen radiocontrole (uit \`docs/data/state.json\`) als de nieuwste workflow-uitvoering rechtstreeks via de openbare GitHub Actions API. Daardoor lijkt de tijd niet langer onbeperkt vast te lopen wanneer er geen nieuwe letter is.
- Als de opgeslagen controle ouder is dan 25 minuten, verschijnt de melding "Controle vertraagd". GitHub kan een geplande workflow vertragen of overslaan; dit kan niet worden gegarandeerd.
- Een korte opname loopt maximaal ongeveer 12,5 minuten. Het GitHub Actions monitorproces heeft een timeout van 20 minuten, zodat de volgende scan niet voortdurend blijft wachten.
- Zodra een Metallica-nummer is waargenomen, maakt \`notify.py\` maximaal één GitHub-issue per uitzending met een vermelding van \`@GingeroDiablo\`. Bij een later automatisch lettervoorstel volgt maximaal één nieuw commentaar per veranderd voorstel. Herhaalde controles geven geen dubbele meldingen. Meldingen werken alleen als de GitHub-workflow daadwerkelijk draait.

**Push aanzetten op Android:** installeer [GitHub Mobile](https://github.com/mobile), meld je aan met \`GingeroDiablo\`, ga naar Profiel → Settings → Configure Notifications en schakel **Direct mentions** in. Schakel daarnaast meldingen voor de GitHub-app in bij Android-instellingen. Optioneel kun je op de repository **Watch → Custom → Issues** inschakelen. Zet niet alle workflow-succesmeldingen aan als je geen melding bij iedere controle wilt.

**Let op:** de GitHub-koppeling kan GitHub-issues aanmaken, maar kan niet de notificatie-instellingen of de app op je telefoon configureren. En een succesvolle scan zonder Metallica of letter veroorzaakt bewust geen pushmelding.


## Hoe werkt het?

```text
KINK lijst (rang / titel) + KINK gedraaid (tijdstippen)
            | (GitHub Actions: iedere 5 minuten gepland)
            v
       Metallica in de buurt?
            |
      Nee: stoppen (weinig rekenwerk)
            |
      Ja: tijdelijke opname op GitHub-runner
            |
       ffmpeg + gratis offline Whisper (faster-whisper)
            |
       voorstel + transcript => docs/data/state.json
            |
       GitHub Actions deployt /docs (ook na bot-commit)
            |
       GitHub Pages => dashboard op telefoon/PC
```

De **live audio wordt niet in de repository opgeslagen** en wordt na verwerking van de runner verwijderd. Alleen de (kort gehouden) transcriptie en onbevestigde suggesties gaan in een JSON-bestand.

## Installatie met GitHub Desktop (makkelijkste)

1. Download `KINK_GitHub_Gratis.zip` uit het ChatGPT-antwoord. Pak het ZIP-bestand uit, zodat je de map `KINK-GitHub-Gratis` ziet.
2. Installeer [GitHub Desktop](https://desktop.github.com/) en log in op je gratis GitHub-account.
3. Kies **File → Add Local Repository → Choose...**, wijs de uitgepakte map aan en kies **Create a Repository** als Desktop daarom vraagt.
4. Klik **Publish repository**, kies een naam (bijv. `kink-lettermonitor`), zorg dat **Keep this code private UIT staat** (publieke repository), en publiceer.
5. Open de repository op github.com. Ga naar **Settings → Pages → Build and deployment** en kies bij **Source** de optie **GitHub Actions**. Dat is nodig voor het publiceren na automatische updates.
6. Open **Actions → KINK Metallica lettermonitor → Run workflow** om de eerste controle én de dashboardpublicatie te starten. (Een push op `main` kan dit ook al automatisch starten.)
7. Bekijk de workflowstatus en open bij **Settings → Pages** de gepubliceerde website. De URL is doorgaans `https://JOUWNAAM.github.io/kink-lettermonitor/`.
8. Mocht de workflow op de publicatiestap een toestemmingsfout geven, controleer dan **Settings → Actions → General → Workflow permissions** en of Pages is geactiveerd. De workflow zelf vraagt `contents: write` en `pages: write` aan.

De monitor controleert daarna automatisch met een **gepland interval van vijf minuten**. Bij gewijzigde resultaten voert de workflow ook expliciet een Pages-deploy uit; zonder die stap zouden bot-commits niet zichtbaar worden op de website. Starttijden zijn niet gegarandeerd. De workflow doet buiten de wedstrijdperiode in 2026 geen werk; verwijder de workflow na afloop om toekomstige cron-aanroepen volledig te stoppen.

### Alternatief met Git

Maak eerst op GitHub een nieuwe **openbare, lege** repository zonder README aan. Voer in de uitgepakte projectmap uit (pas gebruikersnaam/repository aan):

```bash
git init -b main
git add .
git commit -m "KINK monitor GitHub edition"
git remote add origin https://github.com/JOUWNAAM/kink-lettermonitor.git
git push -u origin main
```

Daarna stappen 5–8 hierboven.

## Reparatie 21 oktober 2026: gesproken letters vóór én na Metallica

De eerste uitvoeringen **konden niet opnemen** omdat de Ubuntu-GitHub-runner
geen `ffmpeg` bevatte. De workflow installeert dat programma nu expliciet,
controleert dat het werkt en test of de hoofdzender KINK daadwerkelijk audio
uitstuurt. Bij falen zoekt hij een alternatieve KINK-stream in AAC of MP3.
Zo meldt de app geen geslaagde audiocontrole wanneer de stream ontbreekt.

De monitor begint **voor** het nummer als een bekende Metallica-positie
binnen circa zeven lijstposities nadert. Hij luistert maximaal ongeveer
vijftien minuten en kan twee aparte bestanden maken:

- `-voor.mp3`: ongeveer de twee minuten vóór het begin plus een kort stukje erna;
- `-na.mp3`: ongeveer tachtig seconden vóór het volgende nummer plus een
  stukje erna.

Beide fragmenten worden afzonderlijk door Whisper onderzocht. Eén expliciete
letter is een **onbevestigd voorstel**, geen zekerheid; bij tegenstrijdige
letters vraagt de app om een menselijke controle. Als de opname te laat begon,
kan het ontbrekende deel **niet achteraf** worden teruggehaald. Daarom zijn
de nachtelijke herhalingen bij KINK belangrijk.

De **geheime top 10** mag extra Metallica-nummers bevatten. De monitor
houdt alle nieuw gesignaleerde Metallica-titels bij, ook als er nog geen
positie bekend is, en houdt tijdens de laatste uren van 30 oktober
rekening met nog niet gepubliceerde top-10-noteringen. Onbekende titels
krijgen tijdelijk `#?` en worden later waar mogelijk aan hun echte
positie gekoppeld.

**Grenzen:** GitHub Actions starttijden zijn niet gegarandeerd en een
uitgezonden letter kan dus ondanks deze reparaties gemist worden.
Vooraf aangekondigde letterfragmenten die vóór het begin van een GitHub-run
vallen, zijn niet terug te winnen. De audio-artifacts zijn maximaal
drie dagen beschikbaar, alleen als werkelijk een opname is gemaakt.

## Korte terugluisterfragmenten (GitHub-artifact)

Wanneer de radiomonitor een Metallica-uitzending **echt opneemt**, maakt hij waar mogelijk twee kleine MP3's: vóór de start en rond het einde, ook als maar één van beide tijdstippen bekend is. De codeletter wordt mogelijk tussen de liedjes genoemd; daarom begint het fragment ook een stukje vóór het tijdstip waarop het volgende liedje in KINKs afspeellijst staat. Het bestand kan dus ook enkele seconden muziek bevatten.

**Belangrijk:** GitHub Pages is een openbare statische site en kan niet met jouw GitHub-account een beschermd Actions-artifact streamen. Daarom is er bewust **geen rechtstreeks afspeelbare externe audio-URL** in het publieke dashboard.

Terugluisteren:
1. Ga in **Opnames & aanwijzingen** naar een waarneming waar **Download audiofragment (ZIP)** staat.
2. Klik de link, log zo nodig in op GitHub en download het artifact. Pak het ZIP-bestand uit op je telefoon of computer.
3. Klik bij die opname op **Beluister MP3**, selecteer het uitgepakte MP3-bestand en luister via de speler die daar verschijnt. Het bestand wordt alleen lokaal in je browser geladen, niet naar GitHub Pages verstuurd.
4. Zoeken naar een oude uitzending zonder downloadlink heeft geen zin: GitHub kan opnamefouten, gemiste triggers en ontbrekende eindtijden niet achteraf herstellen.

Technisch: `audio_clips.py` schrijft naar `artifact_audio/` (genegeerd door Git), `actions/upload-artifact@v4` bewaart de MP3 **drie dagen**, en de upload-ID komt pas na een geslaagde upload via `audio_clips.py` in `docs/data/state.json`. De clip wordt niet naar `docs/` gekopieerd. Na het verlopen van GitHub's artifactbewaring werkt de downloadlink niet meer.

**Rechten/privacy:** ook een kort radiofragment kan beschermd zijn. Een artifact van een **openbare repository is niet privé**; beperk gebruik tot wat je rechten en de regels van KINK toestaan. Voor permanent publiek afspelen of het verspreiden van opgenomen radiogeluid is doorgaans toestemming nodig.


## Dashboard en opslag

- De **officiële** Metallica-trackposities worden automatisch uit de KINK 1500 herlezen; de 11 nu publiek bekende posities zitten als startlijst in het project. Als KINK de top 10 nog niet heeft bekendgemaakt, kan een Metallica-nummer tijdelijk met positie **?** verschijnen. Zodra de ranking officieel bekend is, wordt de positie hersteld.
- Bij uitzendmeldingen toont het dashboard datum, transcript en eventueel **lettervoorstel**.
- Klik een nummer aan om zelf **één letter A–Z** te bevestigen. Die bevestiging blijft **uitsluitend in de lokale opslag van die browser** (privacy, geen GitHub-login/API-sleutel in de publieke browser).
- Gebruik **Back-up JSON / Importeer JSON** voor overdracht tussen telefoon/computer of bij browserreset.
- **CSV-export** voor een eigen overzicht; je codewoord kun je zelf vormen met de verzamelde letters.
- De app publiceert geen audioclips op GitHub Pages. Tijdelijke audiofragmenten worden alleen via GitHub Actions-artifacts aangeboden; automatische letterherkenning kan verkeerd gaan.

## Waarom een openbare repository?

Volgens de officiële GitHub-documentatie zijn **standaard GitHub-hosted Actions-runners in openbare repositories gratis**; op GitHub Free is GitHub Pages ook beschikbaar voor openbare repositories. Private repositories hebben andere limieten, waardoor 5-minutencontroles niet binnen het gewone gratis maandbudget passen.

## Technische grenzen

- De geplande vijf minuten zijn **geen belofte**: GitHub documenteert vertragingen en mogelijk overgeslagen runs.
- De app voorspelt een naderend Metallica-nummer door **track en positie** in de gepubliceerde afspeellijst te vergelijken met de volledige officiële hitlijst. De site kan vertraagd of onbereikbaar zijn.
- Audio wordt pas opgenomen **als een hitlijstpositie in de buurt komt**, niet continu. Een aankondiging vóór het opnemen wordt gemist; de KINK-herhaling kan helpen.
- Nachtelijke herhaling (volgens KINK tussen 19:00 en 08:00) kan een tweede detectie opleveren; een nummer telt maar één keer voor de code.
- De **spraakherkenning is gratis**, maar het model `base` wordt pas bij de eerste echte opname gedownload. Downloadtijd, geluidskwaliteit en muziek onder de stem beïnvloeden de transcriptie.
- GitHub Pages kan na een JSON-commit enkele minuten nodig hebben om bijgewerkt te worden. De app ververst de status in de browser om de twee minuten.
- Actie eindigt op 30 oktober; het script accepteert de nachtherhaling tot 31 oktober vóór 08:00. De officiële winnaar wordt 2 november bekendgemaakt.
- Alle JSON-resultaten, inclusief gevonden letters en transcripten, zijn publiek op GitHub. Zet er **geen persoonlijke gegevens, geheimen of API-sleutels** in.
- **De officiële wedstrijdinzending moet je zelf doen op KINK.nl.**

## Repareren / testen

Open **Actions → KINK Metallica lettermonitor → meest recente run** voor foutmeldingen. Bij lege of verkeerd gelezen KINK-pagina's verschijnt de fout ook in het dashboard wanneer die opgeslagen kan worden. De radiostream staat in `.github/workflows/kink-monitor.yml` en kan veranderd worden als KINK een ander kanaal gebruikt. Gebruik alleen het *hoofdkanaal*, niet Distortion of Classics.

Tests lokaal: `python -m pip install -r requirements.txt pytest` en `python -m pytest -q`.

## Bestanden

| Pad | Doel |
| --- | --- |
| `.github/workflows/kink-monitor.yml` | geplande GitHub Actions-taak + opslag + expliciete Pages-publicatie |
| `monitor.py` | officiële KINK-pagina's lezen, kort opnemen, spraakherkenning |
| `docs/index.html` | GitHub Pages dashboard |
| `docs/assets/app.js` en `style.css` | knoppen, letters, lokale back-up, styling |
| `docs/data/state.json` | publiek leesbare status + voorgestelde letters |
| `tests/test_monitor.py` | parser, timing, deduplicatie en lettertests |

Bronnen: [KINK-actie](https://kink.nl/nieuws/kink-stuurt-je-naar-metallica-in-las-vegas-tijdens-de-kink-1500), [officiële KINK 1500](https://kink.nl/hitlists/kink-1500), [KINK gedraaid](https://kink.nl/gedraaid), [GitHub Actions planning](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule), [gratis GitHub Actions](https://docs.github.com/en/actions/concepts/billing-and-usage), [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).