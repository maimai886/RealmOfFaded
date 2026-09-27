# AssetHub 調查

2026-09-17 調查。目的只有一個：評估 AssetHub 能不能拿來生地圖的場景素材，
也就是建築、擺設、地標、岩石樹木這一類道具。角色那條線使用者另外決定，
這份文件只把事實和代價攤開，不替他選。

調查方式是讀官方網站、條款、部落格、官方 CLI 的說明檔，沒有註冊、沒有登入、
沒有下載、沒有付費、沒有留任何資料。所以凡是要登入才看得到的東西，這份文件都列在第 8 節。

2026-09-24 註記：文中拿來對照的 Meshy 產線、`docs/Meshy使用說明.md` 和 `assets/generated/models/meshy/` 都已經清掉，
引用到的路徑只當當時的紀錄，現在的做法看 `docs/美術產線操作手冊.md`。

---

## 0. 這一版更正了上一版的一個錯誤判斷

**上一版把「零件切割」判成對我們沒用，理由是循環論證，這一版更正。**

上一版寫的理由是「`import_glb` 第一件事就 `join()` 掉」。那是拿現有管線的限制
去證明那個限制是對的。我們會 `join()` 是因為 Meshy 從來只給得出一整塊融合網格，
不是因為我們不想要零件。事實上專案裡**已經有一套在跑的零件系統**：
`src/world/actors/character_parts.gd` 的 `SOCKETS` 五個掛點，
身體一個 glb、頭髮一個 glb、每件裝備一個 glb，分層組出來。

更正之後查到的東西比原本的判斷重要得多，重寫在第 6 節和第 7 節：

- AssetHub 的零件**是真的可分離的獨立檔案**，而且每個零件有自己的 UV 和自己的貼圖
- 上一版說「UV 碎不碎畫面上無感」，那句話只在**整塊不拆**的前提下成立。
  一旦要把零件拆開各自使用，它就不成立了，而且專案裡已經有一個量得出來的例子
- 但是專案裡**也已經有一條零件管線**，`cleanup.py` 的 `split_group`，它跑過、成功了、
  產物在磁碟上沒人用。所以「沒有任何管線做得出來」也不是事實，
  真正的差別比那句話細，寫在第 7.2 節

結論本身沒有翻盤，但是理由換了，而且多出一個原本沒看到的用途。

---

## 1. 一句話結論

**對地圖素材：現階段不值得為了它付年費，但是理由和上一版不同。**
它底下接的就是我們已經在用的 Meshy，同一次生成在它那邊要花大約兩倍的錢；
它真正獨有的能力是零件切割，而零件切割對**建築模組件**有一個它自己文件寫明的致命限制，
對**散裝小道具**則已經被我們現有的三十點六件那一招用十四分之一的價錢做掉了。

**對角色裝備：它是目前唯一做得到某一件事的工具，而那件事正好對到一個沒解的洞。**
`characters_real` 這一套的裝備外觀掛零件是 **0 件**，要 16 件，現在全靠跨套退路去拿
名義上已作廢的 `characters/` 那一套。AssetHub 能從一張「穿好裝備的角色」概念圖裡
把衣服、披風、頭盔各自拆成獨立模型，**我們現有的管線做不到這一件事**。
角色要不要走這條路是使用者的決定，這裡只把數字放上來，見第 7.3 節。

理由濃縮成四條：

1. **多的那一層錢，大部分買到的是重拓樸和重展 UV。**我們的 `cleanup.py` 拿到模型之後是
   減面到三千三角形、重算法線、然後把 Meshy 的 PBR 整套丟掉只留 albedo 當底色，
   明暗由 `style.py` 用 mpalette 的光向量重算。**整塊不拆**的道具走這條路，
   碎片圖集沒有成本，因為我們不手繪貼圖、不平鋪、不重烘
2. **但是一旦要拆零件，碎片圖集就有成本了，而且量得出來。**見第 6.3 節：
   `weapons_starter` 切出來的六把武器，每一把都各自拖著一份
   **2,258,794 位元組的同一張圖集**，六份逐位元相同。每一把實際用到的只有六分之一
3. **重拓樸會把貼圖作廢。**官方自己寫的：重拓樸重建表面，之前的 UV 描述的是
   一個已經不存在的網格，所以跑完重拓樸要再花六十點以上重新生貼圖。
   我們現在的減面是在 Meshy 的網格上做的，UV 和貼圖都還在，**不用再付一次錢**
4. **最大的風險是授權，而且是踩下去就完蛋的那一種。**免費方案生出來的東西**權利歸 AssetHub**，
   只能個人非商用，而且不得轉授權給第三方。把它放進要營運的 MMO 客戶端是直接違約。
   商用一定要在付費方案期間生成，這一點和 Meshy 一樣

**值得花錢去試的兩件事**，在第 5 節和第 7 節講：

- 我們當初否決 Meshy 做道具的理由不是拓樸也不是 UV，是**整組偏同一個木頭橘、色塊分不開**。
  AssetHub 有一個 Meshy 沒有的東西，用 Nano Banana 的 AI 重新生貼圖。
  那是唯一有可能真的解掉當初那個問題的功能
- 零件切割能不能真的產出掛得上 `hand_r` 的那種 glb。**關鍵未知數是原點在哪裡**，
  官方文件完全沒寫，見第 6.2 節

---

## 2. 價錢

訂閱制加點數制，兩種混在一起：訂閱買到的是每年一包點數，每一次生成扣點數。
以下數字都是 2026-09-17 從 https://assethub.io/pricing 抄的。

### 方案

| 方案 | 年繳 | 換算每月 | 年度點數 | 每點成本 | 商用 |
|---|---|---|---|---|---|
| Free | $0 | $0 | 4,200 | — | **不可以** |
| Pro | $192 | $16 | 9,600 | $0.020 | 可以 |
| Max | $576 | $48 | 36,000 | $0.016 | 可以 |
| Studio | $960 | $80 | 66,000 | $0.0145 | 可以 |
| Enterprise | 議價 | — | 議價 | — | 可以 |

月繳比年繳貴兩成。官方只明講 Pro 月繳是 $20，Max 和 Studio 的月繳價照同一個比例
推算是 $60 和 $100，這兩個數字沒有被官方文字直接證實。

點數包可以單買，任何方案包括免費方案都能買：

| 價錢 | 點數 | 每點成本 |
|---|---|---|
| $12 | 400 | $0.030 |
| $60 | 2,000 | $0.030 |
| $216 | 8,000 | $0.027 |
| $1,250 | 50,000 | $0.025 |

點數包買了一年內有效。訂閱的點數每個結帳週期重發，官方沒說沒用完會不會累積，
寫法是「replenished every billing period」，看起來是不累積。

### 一次操作要幾點

價目頁的官方表：

| 操作 | 點數 | 換算成錢，用 Pro 年繳每點 $0.02 算 |
|---|---|---|
| 圖生 3D，可選 Tripo、Rodin、Meshy、Hunyuan、Hitem3D | 25–140 | $0.50–$2.80 |
| AI 生貼圖 | 60 起 | $1.20 起 |
| 自動綁骨 | 50 | $1.00 |
| AI 重拓樸 | 25–75 | $0.50–$1.50 |
| 重展 UV | 15 | $0.30 |
| 概念圖或參考圖 | 2–8 | $0.04–$0.16 |

部落格再拆細一層，這幾個數字對我們比較重要：

- **Tripo 3.1**，它的預設生成模型。標準 2K 貼圖加標準幾何是 25 點，
  4K 是 35 點，8K 是 45 點；換成 Ultra 幾何分別是 45、50、60 點。
  介面預設就是 50 點那一檔
- **Meshy V6** 在它平台上跑是 **60 點**，開 extreme texture 是 70 點
- **Tripo P1.0** 是 85 點，特色是生成當下就產 UV，面數上限兩萬
- **重拓樸**：Tripo 是 25 點，開 Smart Low-Poly 變 50 點，Hunyuan3D 是 75 點
- **重展 UV** 固定 15 點，沒有任何參數可以調
- **概念圖清乾淨** 5 點一張，**多視角** 5 點一個視角，四個視角就是 20 點
- **零件切割**分兩段收費：分析那一段 **2 點**，找出有哪些零件並判斷姿勢；
  執行那一段 **50 點**，產出每個零件的視圖。**之後每一個零件各自算一次生成**，
  Tripo P1.0 是 85 點，Meshy V6 是 60 點，Hitem3D v2.1 Pro 是 115 點

出處：
- https://assethub.io/pricing
- https://assethub.io/blog/tripo-3-1-the-essentials
- https://assethub.io/blog/meshy-v6-the-essentials
- https://assethub.io/blog/ai-retopology
- https://assethub.io/blog/automatic-uv-unwrapping
- https://assethub.io/blog/how-to-convert-2d-concept-art-to-3d-game-asset
- https://assethub.io/blog/separate-3d-model-into-parts

### 有沒有隱藏的加價

有，而且是我們最該注意的地方。**高解析貼圖、重展 UV、重拓樸三件事各自算錢，
不是包在生成裡的。**照它自己的教學走完一件場景道具的完整流程：

| 步驟 | 點數 |
|---|---|
| 概念圖清乾淨 | 5 |
| 四個視角 | 20 |
| Tripo 3.1 生成，預設檔 | 50 |
| AI 重拓樸，Tripo | 25 |
| 重展 UV | 15 |
| **重拓樸之後貼圖作廢，重新生一次** | 60 |
| 合計 | **175 點，約 $3.50** |

如果只生不整理，Tripo 3.1 最便宜那一檔是 25 點，約 $0.50。
兩個數字差七倍，中間的差額就是它賣的那一層。

一座城鎮要一百件道具的話：走完整流程是 17,500 點，Pro 方案一年的點數不夠，
要買到 Max。只生不整理是 2,500 點，Pro 綽綽有餘。

---

## 3. 授權

條款本體在 https://assethub.io/terms-of-service ，標示 Established on June 1, 2026。
準據法是美國德拉瓦州。公司登記地址寫的是德拉瓦州多佛，舊金山那個地址出現在隱私權政策的
GDPR 條款裡。

### 3.1 生出來的模型權利歸誰，能不能商用

**付費方案：權利歸我們，可以商用。**原文第 4 條第 2 項：

> With respect to the paid plans of the Service, all intellectual property rights and any other
> rights in the Outputs generated through use of the paid plans shall belong to the User or to the
> third party that is the rights holder of the Information. Users of paid plans may use the
> generated Outputs for any purpose, including commercial use, provided that such use does not
> violate the prohibited acts set forth in these Terms.

「any purpose, including commercial use」這個寫法比 Meshy 的說明文件明確，
Meshy 那邊是幫助中心的文章，AssetHub 這句寫在條款本體裡。這一點是加分的。

出處：https://assethub.io/terms-of-service 第 4 條

### 3.2 免費方案和付費方案的授權完全不一樣

**這是整份調查最危險的一條。**原文第 4 條第 1 項：

> With respect to the free plan of the Service, all intellectual property rights and any other
> rights in the outputs generated through use of the free plan (hereinafter referred to as
> "Outputs") shall belong to the Company. Users of the free plan may use the generated Outputs
> solely on a non-exclusive basis for personal and non-commercial purposes and shall not
> sublicense or assign such Outputs to third parties without the Company's consent.

拆開講：

- 免費方案生出來的東西，**智慧財產權歸 AssetHub 公司所有**，不是歸我們
- 我們只拿到一個非專屬的使用權，而且**限個人、非商業用途**
- **不得轉授權或讓與給第三方**

這比 Meshy 的免費方案嚴厲得多。Meshy 免費方案是 CC BY 4.0，可以商用只要標註；
AssetHub 免費方案根本不能商用，而且模型不是我們的。把免費方案生的東西放進要營運的
遊戲客戶端，是同時踩到「商業使用」和「散布給第三方」兩條。

價目頁上還有一個會害死人的矛盾：Free 方案的卡片上印著「Commercial use」這一行，
但是同一頁下面的常見問答寫的是

> Can I use the assets commercially?
> Yes, on any paid plan (Pro, Max, Studio). The Free plan is for evaluation only.

**卡片上那一行是錯的或是排版問題，以條款和問答為準：免費方案不能商用。**
如果真的要用，建議先寫信去 info@assethub.studio 要一句白紙黑字的回覆再動手。

第 6 條的禁止行為清單裡還有一條專門針對這件事：

> Disguising free plan outputs as paid plan outputs (output laundering)

也就是說他們預期有人會想用免費額度生完再假裝是付費生的，這條明文禁止。

出處：https://assethub.io/terms-of-service 第 4 條第 1 項、第 6 條；https://assethub.io/pricing 常見問答

### 3.3 有沒有禁止轉售、禁止拿去訓練 AI

**禁止轉售：條款裡有一條，但是它禁的是「服務」不是「產出」。**第 6 條原文：

> Redistribution and lending of part or all of the Service (including copies), and resale or
> transfer of the Service

主詞從頭到尾是 the Service，指的是 AssetHub 這個平台本身、它的程式和帳號，
不是我們生出來的模型。加上第 4 條第 2 項明講付費產出可以「any purpose」，
**把模型包進遊戲客戶端出貨不是轉售服務，這一條管不到我們。**
這比 Meshy 的情況清楚，Meshy 官方說明完全沒提能不能再散布，我們自己在
`docs/Meshy使用說明.md` 第 6 節留了一條「超出範圍先去問官方」。AssetHub 這邊不需要那條。

**禁止拿去訓練 AI：條款裡沒有這種條款。**我把第 6 條十七條禁止行為逐條看過，
沒有任何一條限制我們用產出去訓練模型。

反過來，**他們會不會拿我們的東西去訓練**，兩份文件互相打架：

隱私權政策第 3 條說得很乾脆：

> The Company does not use user content or outputs for the training or development of AI models.
> User data is processed only to the extent necessary for the provision of the Service.

但是服務條款第 1 條第 1 項描述服務內容的時候是這樣寫的：

> Users may use the Service to generate outputs ... by having the Company's AI models learn
> (including re-learning and fine-tuning; the same shall apply hereinafter) or by inputting into
> prompts information such as image data ...

而第 5 條第 1 項的承諾是：

> The Company shall not use the Information that Users have had the AI Models learn or have input
> into prompts, or the Outputs generated by Users through their use of the Service, for the benefit
> of any third party other than the Company and such User.

注意最後那半句：不給**除了公司和該使用者以外**的第三方。**公司自己用是不在禁止範圍內的。**
隱私權政策那句比較寬，條款這句比較窄，兩份文件位階上條款通常優先。
我們送進去的概念圖本來就是自己產的，不是什麼機密，所以實務上風險低，
但是如果哪天要送客戶的原畫或未公開的美術進去，這個差異就要先問清楚。

出處：https://assethub.io/terms-of-service 第 1、5、6 條；https://assethub.io/privacy-policy 第 3 條

### 3.4 素材會跑到第三方的伺服器上，而且他們不保證第三方怎麼用

這一條 Meshy 沒有，是 AssetHub 這種轉包架構特有的。第 5 條第 2 項：

> ... the Information that Users have had learned or input into prompts, and the Outputs generated
> through such use, may be stored on servers managed by such external service providers. The
> Company is not aware of whether such external service providers may use such Information and
> Outputs for purposes other than the purpose intended by the User; therefore, Users are required
> to review the terms of service of such external service providers for details.

白話講：**AssetHub 自己說它不知道 Meshy、Tripo、Hunyuan、Rodin、Hitem3D、Nano Banana
這些上游拿我們的東西去做什麼，要我們自己去看那六家的條款。**
所以 AssetHub 給我們的授權保證，管不到上游那一層。我們現在直接用 Meshy，
只要看一家的條款就好，換成 AssetHub 要看七家。這是多一層轉包必然的代價。

再配上第 10 條第 1 項的免責：

> That the Service does not infringe any intellectual property rights or other rights of third
> parties

也就是**它不保證產出不侵害第三方權利**，出事我們自己扛，而且第 10 條第 3 項要我們
連律師費一起賠給他們。這一段和 Meshy 的免責差不多，業界都這樣寫，不是它特別壞。

出處：https://assethub.io/terms-of-service 第 5 條第 2 項、第 10 條

### 3.5 MMO 客戶端會被玩家挖素材，條款有沒有管

**條款完全沒有提到這件事。**我把十四條逐條看過，沒有任何條文談嵌入軟體、
嵌入遊戲、或是終端使用者能不能取得素材檔。

推論如下，這是推論不是條文：

- **付費方案下沒問題。**第 4 條第 2 項把權利整個給我們了，模型是我們的財產。
  玩家從客戶端挖走素材是每一款遊戲都有的問題，那是我們和玩家之間的事，
  和 AssetHub 沒有關係，條款也沒有給我們任何保護素材的義務
- **免費方案下是災難。**第 4 條第 1 項的權利在 AssetHub 手上，
  我們連「不得轉授權或讓與給第三方」都做不到。遊戲客戶端本質上就是把檔案送到玩家電腦上，
  這件事在免費方案下講不過去

所以這一題的答案還是回到同一句：**一定要在付費方案期間生成。**

### 3.6 停止付費之後之前生的還能不能用

**條款沒有寫終止後的效力條款，這是它的缺口。**沒有 survival clause，
沒有一句「終止後先前產出的授權繼續有效」。

從條文結構推論，結論偏正面：第 4 條第 2 項是**權利歸屬**的寫法，不是**授權**的寫法。
「shall belong to the User」是所有權移轉，發生在產生的那一刻。
所有權一旦移轉，不會因為之後退訂而回去。這和 Meshy 的規則一致，
`docs/Meshy使用說明.md` 第 0 節記的就是「權利跟著產生當下的方案走」。

但是有兩個實際的風險，和權利無關：

1. **檔案的取用權沒有保證。**第 9 條第 2 項寫公司可以自行決定終止服務的全部或一部，
   第 7、8 條寫公司可以停權。帳號沒了，放在他們那邊的檔案我們就拿不到了。
   **對策：每一件生出來的東西當天就下載回來進版本庫，不要把他們的網站當成資產倉庫。**
   這一點我們對 Meshy 已經在做，`art_source/meshy/raw/` 就是幹這個的
2. **條款隨時會改。**第 14 條寫公司可以改條款，只在網站貼出來，繼續使用就視為同意。
   條款本身是 2026 年 6 月才立的，公司是 2023 年成立、拿了兩百萬美元種子輪的早期團隊。
   一份三個月大的條款配一家新創公司，對一款要長期營運的商業遊戲來說，
   **訂閱證明和下載存檔的價值遠大於文件裡的任何一句話。**建議照 Meshy 那邊的做法，
   帳單和方案頁截圖自己留一份

出處：https://assethub.io/terms-of-service 第 4、7、8、9、14 條

### 3.7 授權部分的結論

| 問題 | 答案 |
|---|---|
| 付費方案的產出歸誰 | 歸我們，可以商用，條款第 4 條第 2 項白紙黑字 |
| 免費和付費一樣嗎 | **完全不一樣。**免費的權利歸 AssetHub，只能個人非商用，不得轉授權 |
| 禁止轉售嗎 | 禁的是轉售「服務」，不是產出。放進遊戲不算轉售 |
| 禁止拿去訓練 AI 嗎 | 沒有這種條款 |
| 他們會拿我們的東西訓練嗎 | 隱私權政策說不會，條款留了「公司自己用」的空間，兩份文件不一致 |
| MMO 被挖素材 | 條款沒管。付費方案下不是問題，免費方案下是嚴重問題 |
| 停付費之後還能用嗎 | 條款沒寫，但是權利移轉是在產生當下發生，推論可以繼續用。檔案要自己存 |

---

## 4. 輸出格式和 Godot 相容性

### 4.1 能拿到什麼檔

- **GLB**：三角形網格的標準輸出。Godot 4 原生吃 glb，不需要任何轉檔
- **FBX**：只有走四邊形輸出的時候才給 FBX。官方原話是 GLB 不儲存四邊形，
  所以四邊形要靠 FBX 或 OBJ
- **OBJ**：重展 UV 的輸入接受 FBX、OBJ、GLB 三種，所以 OBJ 至少在平台內流通

**多個零件一起匯出的方式是壓縮檔。**零件切割那篇的原文是：在畫布上選取要的零件，
打開 Export Assets，下載回來是一個 ZIP，內容可以選原始檔、GLB 或 FBX。
所以**零件是一個一個獨立的檔案，不是一個 glb 裡的多個節點**，這一點很重要，
第 6 節整節在講。

它沒有一個公開的「支援格式」頁面，以上是從四篇部落格拼出來的。
價目頁和首頁都沒有列匯出格式，這是它的說明做得比 Meshy 差的地方。
Meshy 有一頁 https://docs.meshy.ai/en/webapp/guides/platform/export-formats 講得清清楚楚。

**對我們來說 GLB 就夠了，而且是唯一要的。**`art_pipeline/meshy/config.py` 裡
`TOPOLOGY = "triangle"`，註解寫的理由是「Blender 匯入和減面都比較單純」。
四邊形對我們沒有用，所以 FBX 那條路可以完全忽略。

### 4.2 Godot 吃不吃得下

**吃得下，不用轉檔。**Godot 4 原生匯入 glb 和 gltf，我們現在整條管線
`cleanup.py` 的 `export_prop` 輸出的就是 glb，走的是同一條路。

AssetHub 自己在 Tripo 3.1 那篇有提到 Godot，說輸出是完整的 PBR 材質組
而不是一張烘死的貼圖，可以在 Unity、Unreal、Godot、Blender 裡對引擎光源起反應。
這一點對我們沒有意義，因為 `style.py` 會把整組 PBR 丟掉只留 albedo，
材質改成自發光的，場景不放燈。那是 mrender 的前提。

### 4.3 有沒有綁定 Blender 或 Maya

**沒有綁定。**網站頁尾有兩條叫「Warrior (Blender pipeline)」和「Theron (Maya pipeline)」的
連結，那是兩個範例工作流不是必要條件。平台本身是網頁版的節點畫布，
檔案直接從網頁下載，不需要裝任何外掛。

它另外有一套官方 CLI 和 MCP，見第 6 節，那個反而對我們比較有用。

### 4.4 貼圖是幾張、什麼通道

- 出來的是**完整的一組 PBR**，不是單張烘死的貼圖。部落格原文是
  「Output includes a full PBR material set rather than a single baked texture」
- 走 Tripo 低面數重拓樸那條路的時候，**顏色、金屬度、粗糙度、法線**四張會一起保留
- **解析度分三檔**：標準 2K、HD 4K 是介面預設、8K。三檔的點數不一樣，見第 2 節
- **重展 UV 沒有任何參數可以調**，包括貼圖大小

我們只會用到 albedo，而且 `config.py` 裡 `TEXTURE_RESOLUTION = "2k"`。
所以 AssetHub 的 4K 預設對我們是純浪費，**每一次生成要記得手動調回 2K，
可以省十到二十點**。

出處：
- https://assethub.io/blog/tripo-3-1-the-essentials
- https://assethub.io/blog/ai-retopology
- https://assethub.io/blog/automatic-uv-unwrapping

---

## 5. 拿來做場景道具合不合適

### 5.1 它主打的確實是角色，不是場景

證據一面倒：

- 首頁的流程描述是「一張概念圖切成有名字的零件，再組裝起來」，
  範例是角色的頭髮、盔甲、武器這種可替換零件
- 社群展示區四個精選作品全部是角色：Theron、Warrior、Sara、char02_Pulse_Hair
- 教學影片三支，「How To Separate Parts」「How To Merge Parts」「I Built a Modular Character with AI」，
  全部是角色
- 部落格五篇，全部在講概念圖轉角色模型和各家生成模型的比較，**沒有一篇談場景或建築**
- 官方 CLI 的零件切割模型叫 `Chibi Character (Pluffy) v3.1`，名字就寫著角色

**唯一和建築沾到邊的線索**是 CLI 說明檔裡提到一個叫「V3.7.1 Building Modules」的
內部技能類別，還有一段 storyboard 工作流用了「Reconstruct this storyboard as a 3D scene」
這種指令。兩者都是內部功能或實驗性的，一般帳號拿不到，也沒有任何成果可以看。

**結論：沒有找到任何人拿它做場景，官方也沒有這類範例。**

它的零件切割能不能拿來做**模組化建築**，這是上一版漏掉的一個用途，
單獨寫在第 6.4 節。短答案是它自己的文件就寫了一條會讓這個用途破功的限制。

### 5.2 但是底下的生成模型是通用的

這一點要講公道話。AssetHub 自己不做生成，它是把別人的模型串起來。
底下這幾家做建築和岩石樹木都沒問題：

- **Hitem3D v2.1** 官方定位是硬表面專用，講明了做載具、武器、機械。
  建築和市集攤位這種東西正好是硬表面
- **Tripo 3.1** 是通用的，就是我們要的那種東西
- **Meshy V6** 就是我們現在在用的那一個

所以**做不做得出建築不是問題，問題是它賣的那一層價值對場景道具有沒有用。**

### 5.3 面數和拓樸，這是我們最在意的

手機也要跑、一個城鎮上百個道具，這個要求對它的規格是這樣對的：

| 項目 | AssetHub | 我們的規格 |
|---|---|---|
| Tripo 3.1 三角形輸出 | 最高 2,000,000 面 | — |
| Tripo 3.1 四邊形輸出 | 500 到 50,000 面 | — |
| Meshy V6 節點 | 300,000 面天花板，而且每一次生成都往上限跑 | — |
| Tripo 重拓樸滑桿 | 500 到 500,000 面 | — |
| Tripo Smart Low-Poly | 三角形 500 到 20,000，四邊形 500 到 10,000 | — |
| Tripo P1.0 | 上限 20,000 面 | — |
| **我們的道具上限** | — | **`PROP_TRI_CAP = 3000`** |

**它最低那一檔 500 面也還在我們的範圍內，所以規格上沒有障礙。**
Smart Low-Poly 的兩萬面和我們的三千差了快七倍，但是 Tripo 的一般滑桿可以直接拉到 500。

拓樸品質上，它自己的部落格講得比行銷話誠實：

> Automatic retopology gives you ... quads, even density, and loops where the model bends

然後馬上補一句只有前兩項做得到，會彎的地方要的線流還是得手工。
對角色來說這是致命的，對**不會動的場景道具來說完全無所謂**。
建築和攤位不綁骨、不彎折，均勻密度就夠了。

**問題是我們已經有一個零成本的替代方案。**`cleanup.py` 的 `cap_polygons` 用 Blender 的
Decimate COLLAPSE 減到上限，最多跑三輪。減面出來的三角形分佈確實不如 AI 重拓樸均勻，
但是對一個三千面、在手機螢幕上只有幾十像素高的攤位，**這個差別看不出來**，
而且減面**保留原本的 UV 和貼圖**，AI 重拓樸則會把貼圖作廢要重新生。

### 5.4 我們當初否決 Meshy 做道具的真正理由

`docs/Meshy使用說明.md` 第 7 節記的是：

> **道具**。第一批實測晨曦鎮的推車和市集攤位，自製的 town_kit 在遊戲距離下讀得比較清楚，
> Meshy 版整組偏同一個木頭橘、失去色塊分離。

**這是貼圖的顏色問題，不是拓樸問題也不是 UV 問題。**
AssetHub 賣的重拓樸和重展 UV 對這個問題一點幫助都沒有。

但是它有一個 Meshy 沒有的東西：**用 Nano Banana 重新生貼圖，60 點起跳**。
那是一個純粹的圖像生成模型在既有 UV 上重畫，理論上可以要求它「色塊分離、
不要整組同一個木頭橘」。**這是整份調查裡唯一有可能真的解掉當初那個問題的功能，
而它和 AssetHub 的主打賣點無關。**

要試的話最小成本是這樣：Tripo 3.1 最低檔 25 點生一個攤位，
再用 60 點重新生一次貼圖，一共 85 點，約 $1.70。
和現有的 Meshy 版並排放進晨曦鎮，照 `docs/Meshy使用說明.md` 第 9.5 節規則二，
在那張地圖的實際底色上判斷。**沒試過之前不要下結論，也不要為了這個買年費。**

出處：
- https://assethub.io/blog/ai-retopology
- https://assethub.io/blog/tripo-3-1-the-essentials
- https://assethub.io/blog/meshy-v6-the-essentials
- https://app.assethub.io 首頁的社群展示與教學影片

---

## 6. 零件切割：它到底產出什麼

上一版把這一節判成「對我們沒用」，理由是循環論證，這一版重查。
主要出處是 https://assethub.io/blog/separate-3d-model-into-parts
和官方 CLI 的說明檔 https://github.com/AssetHub-inc/assethub-cli

### 6.1 它切的是圖不是網格

**這是理解整件事的關鍵，而且和我們的直覺相反。**官方原話：

> It separates from the image, not from your mesh.

流程是這樣：

1. 把一張概念圖丟上畫布，按 Start 3D Production
2. **分析**，2 點。系統判斷姿勢，並且辨識出這個主體有哪些組成零件
3. 人確認要哪些零件
4. **執行**，50 點。產出每個零件的多視角圖
5. **每一個被選中的零件各自被派成一個獨立的圖生 3D 任務**，一個零件一次生成的錢

官方原話是「each selected part is dispatched as its own image-to-mesh job」。
所以它不是把一整塊網格切開，是**在還沒有網格之前就先把圖拆開，然後一件一件分別生成**。

這一條同時解釋了它的兩個特性：

- 拿一個已經做好的融合 glb 給它切，**它不做這件事**。
  官方寫得很白：「Arriving with a finished fused GLB and wanting it cut is not what this does」
- 每一件都是獨立生成的，所以每一件天生就是獨立的模型，不是從一塊上面切下來的

一個角色典型會切出**五到十五件**。

### 6.2 每個零件有沒有自己的原點和貼圖

**貼圖和 UV：有，而且是官方明講的。**原文：

> Automatic UV unwrapping gives each part its own island layout, and AI texture generation
> treats it as a subject in its own right.

每個零件有**自己的一套 UV 島**，AI 生貼圖的時候**把它當成一個獨立的主體**看待。
這正是我們要的，理由見 6.3 節。

**匯出成獨立檔案：可以。**在畫布上選取零件，Export Assets 下載回來是一個 ZIP，
裡面是一件一個檔，格式可選原始檔、GLB 或 FBX。
CLI 那邊也對得起來：`assethub mesh list` 的搜尋範圍明文包含 parts，
每個零件有自己的 mesh id，可以用 `assethub mesh download mesh_123 --out-dir ./meshes`
單獨抓下來。所以零件是第一級的資產，不是某個組合檔裡的子節點。

**原點在哪裡：官方文件完全沒寫，這是最關鍵的未知數。**

這一項決定它能不能直接變成我們掛在 socket 上的那種 glb。
`character_parts.gd` 的 `visual_of()` 其實已經把兩種座標系都考慮進去了：

```gdscript
# 模型是用哪個座標系做的：socket 是原點就在掛點上，body 是用整個身體的座標系做的。
# 武器是 socket，頭飾和頭髮是 body
"space": String(raw.get("space", "socket")),
```

推論是這樣，**這是推論不是查到的**：零件是為了組裝回同一個角色而生的，
所以它們的座標八成是**整個角色的座標系**，也就是我們的 `space: "body"` 那一類。
披風、盔甲、頭飾本來就是 `body` 空間，`items.json` 裡四件披風寫的就是 `"space": "body"`，
**那幾類可能開箱就對**。武器是 `socket` 空間，原點要落在握把上，
那個八成要自己補一步，做法和 `cleanup.py` 的 `_recentre_only` 是同一類的事。

**在沒有實際下載一包零件量過之前，不要把這一項當成已知。**

### 6.3 UV 的判斷要重看，而且專案裡已經有量得出來的證據

上一版寫「UV 碎不碎畫面上無感」。**那句話只在整塊不拆的前提下成立。**
`style.py` 是照原本的 UV 取樣 albedo，只要網格和貼圖是配對的，碎不碎不影響畫面，
這一段沒有錯。**錯的是把這個結論延伸到零件上。**

把一塊融合網格自己切開的時候會發生什麼事，專案裡有現成的例子。
`cleanup.py` 的 `split_group` 把六把武器的合併網格切成六個獨立 glb，
切完每一件都套上同一張圖集：

```python
style.apply_style(obj, image)
```

`image` 是在切割前用 `base_color_image(merged)` 抓的**整組共用那一張**。
結果在磁碟上：

```
assets/generated/models/meshy/weapons_starter/
  bow_Image_0.jpg          2258794
  buckler_Image_0.jpg      2258794
  club_Image_0.jpg         2258794
  dagger_Image_0.jpg       2258794
  short_sword_Image_0.jpg  2258794
  staff_Image_0.jpg        2258794
```

**六個檔案逐位元相同，每一把武器各自拖著整組六件的圖集，自己只用到六分之一。**
六份 2.26 MB 就是 13.6 MB，其中 11.3 MB 是為了畫另外五把武器而載進來的像素。

這不是假設性的擔憂。`docs/效能與記憶體.md` 記著灰蝕地窟 B1 的貼圖是 203.3 MB、
超過 200 MB 的目標，整份文件都在為了幾十 MB 斤斤計較。
**自己切零件會把「UV 碎片圖集」從一個美術上的不方便變成一個記憶體上的浪費，
浪費的倍數就是一張圖集裡塞了幾件東西。**

AssetHub 的零件不會有這個問題，因為它們是**分別生成、分別展 UV、分別上貼圖**的，
一件一張自己的圖，沒有共用圖集可以拖。

**所以第 3 題的答案是：會，UV 的判斷在零件情境下不成立，上一版講得太滿。**
補一句公道話：這件事**不必然要靠 AssetHub 解**。
在 `split_group` 裡對每一件重新展 UV 再把圖集裁切重烘，也能解，那是純 Blender 的工作、
不花點數，但是要寫程式，而且重烘會有品質損失。買 AssetHub 是用錢換這段工，不是用錢買唯一解。

### 6.4 對地圖素材：模組化建築有一條會破功的限制

**這是上一版完全漏掉的用途。**一張房子的概念圖切成屋頂、牆、門、窗、煙囪，
就是一組模組化建築套件，同一組零件可以拼出十棟不一樣的房子。
專案裡本來就有 `town_kit` 和 `assets/generated/models/town/` 兩組在競爭同一個位置，
這個用途是真的對得上的，上一版把它漏掉了。

**但是它自己的文件寫了兩條限制，其中一條對建築是致命的：**

> Parts are generated, not carved ... expect to nudge fits at assembly

零件是**各自生成**的不是從整體上切下來的，所以組裝的時候要手動微調接縫。
對角色來說這沒什麼，一件盔甲和身體差個幾公釐看不出來。
**對模組化建築來說這是致命的**，模組件的整個價值就在於能精準對齊拼接，
一片生成出來的屋頂和一面生成出來的牆之間差百分之三，就永遠拼不起來，
只能一棟一棟手工對，那就不叫模組化了。

第二條限制：

> A component hidden behind another will not be found

被擋住的零件找不到。一張正面視角的房子概念圖裡，背面那一片牆是看不到的，
所以切不出來。

**結論：對地圖素材，零件切割適合「一張圖裡一組各自獨立的散裝道具」，
不適合「要精準拼接的建築模組件」。**而散裝道具那個用途，我們已經有更便宜的做法，
見 7.2 節。

---

## 7. 和現有 Meshy 管線怎麼接，多花的錢換到什麼

這一節動手之前讀過 `docs/Meshy使用說明.md`、`art_pipeline/meshy/cleanup.py`、
`config.py`、`style.py`、`jobs.json`。

### 7.1 清理管線能不能直接吃

**能，而且不用改程式，只要把檔案放對地方。**

`cleanup.py` 的進入點是 `raw_glb(job_id)`，它只做一件事：
找 `art_source/meshy/raw/<id>/<id>.glb` 在不在。它不在乎那個 glb 是誰生的。
之後 `import_glb` 用 `bpy.ops.import_scene.gltf` 匯入，
接下來的減面、平滑著色、縮尺寸、腳底歸零、換材質全部是對 Blender 物件做的，
和來源平台無關。

所以最小可行的接法是：

1. 從 AssetHub 下載 glb
2. 放到 `art_source/meshy/raw/<id>/<id>.glb`
3. 在 `jobs.json` 加一筆，照現有格式寫 `id`、`category: "prop"`、`size_m`、`fit`、`tri_cap`
4. 照常跑 `blender -b --factory-startup --python-exit-code 1 -P art_pipeline/meshy/cleanup.py -- <id>`

`size_m` 和 `fit` 的量法不變，還是從現有美術量出來，
這樣換模型之後遊戲裡的大小不會變。AssetHub 一樣不能相信它給的尺寸。

### 7.2 散裝道具：我們已經有一條零件管線，而且便宜十四倍

上一版說我們沒有零件管線，那不是事實。`cleanup.py` 的 `split_group` 就是一條，
而且**它跑過、成功了、產物在磁碟上**：

```
assets/generated/models/meshy/weapons_starter/
  bow.glb  buckler.glb  club.glb  dagger.glb  short_sword.glb  staff.glb
```

做法寫在 `docs/Meshy使用說明.md` 第 10 節：一張參考圖裡把六件東西排成格子、
彼此留空隙，送一個任務 30 點，回來用連通分量切開，**一個任務 30 點換六件**。
切完每一件各自置中、最低點歸零，還會印出面數、三軸大小和原點對不對。

價錢差距很大：

| | 現有的 `split_group` | AssetHub 零件切割 |
|---|---|---|
| 六件散裝道具 | 一個 Meshy 任務 30 點，約 **$0.60** | 分析 2 + 執行 50 + 六件各 60，共 412 點，約 **$8.24** |
| 一件平均 | $0.10 | $1.37 |

**十四倍。**所以對「一張圖裡一組各自獨立的散裝道具」這個用途，
我們現有的做法便宜得多，沒有理由換。

`split_group` 有兩個真實的缺點，講清楚才公平：

1. **每一件拖著整組的圖集。**第 6.3 節量過了，六份 2.26 MB 逐位元相同。
   這個要修不必買 AssetHub，在 `split_group` 裡對每一件裁圖重烘就好
2. **它只切得開「散開擺的東西」。**連通分量的前提是各件在網格上不相連，
   所以參考圖必須平放俯視、排成格子、彼此留空隙。
   `docs/Meshy使用說明.md` 第 10 節整節在講怎麼排才切得開，
   還警告「兩件靠太近黏成一塊」會切錯件數

第二點就是 AssetHub 真正贏的地方，接下來這一節講。

### 7.3 角色裝備：這是 AssetHub 唯一獨有的能力，對到一個沒解的洞

**這一節只列事實和數字，角色要走哪條路是使用者的決定，不在這裡下結論。**

#### 洞有多大

從 `data/items.json` 和磁碟上數出來的：

| 項目 | 數字 |
|---|---|
| 道具總數 | 69 |
| 其中有 `visual` 外觀的 | 26 |
| 這 26 件指到幾個不同的模型 | 16 |
| 九個職業的預設武器指到的模型 | 9，**全部已經在上面那 16 個裡面**，所以聯集還是 16 |
| **真正要做的掛零件總數** | **16** |
| 掛點分佈 | `hand_r` 13、`hand_l` 4、`back` 4、`body` 4、`head` 1 |
| `characters/` 這一套磁碟上有幾件 | 18 件。多出來的 `circlet` 和 `helm_iron` 沒有任何資料引用 |
| **`characters_real` 這一套有幾件** | **0 件** |

`characters_real` 資料夾裡只有 14 具身體、4 張臉、5 頂頭髮，
**一件武器、一件盔甲、一件披風、一頂頭盔都沒有**。
16 這個數字和 `docs/資產清單與缺口.md` 第 5 節記的「16 件裝備外觀只有它有」對得上。

現在能動的原因是 `character_parts.gd` 的 `model_path()` 有一段跨套退路：

```gdscript
# 先找目前這一套，找不到就照 ART_SETS 的順序往下找。
for name in ART_SETS:
    var path := _exists("%s/%s.glb" % [ART_SETS[name], model_name])
```

所以每一個穿裝備的玩家身上都同時掛著兩套美術的東西，
`docs/資產清單與缺口.md` 第 5 節已經記下來了：刪掉 `characters/` 會讓所有裝備外觀無聲消失。

#### 我們現有的管線做不到哪一件事

`split_group` 切得開**攤平擺開的散件**，切不開**穿在身上的東西**。
一件盔甲穿在角色身上的時候，在概念圖裡和身體是連著的，在生成出來的網格裡也是融合的，
連通分量會把整個角色算成一塊。

`docs/Meshy使用說明.md` 第 9 節記著試過一輪要從融合角色上切東西的結果：
頭髮切出鋸齒缺口、眉毛睫毛被算進頭髮、修了四輪每一輪修好一處就冒出下一處，
最後一項「**還沒解，而且看不出會收斂**」。那一節的結論就是這條路不通。

**AssetHub 的零件切割是在圖的階段拆的，不是在網格上切的**，
所以它從根本上避開了那一節踩到的坑。官方明講切出來的是
「hair, body, clothing, and accessories」，而且每一件**各自生成、各自展 UV、各自上貼圖**。

**這是這次調查裡唯一一件「只有它做得到」的事。**

#### 如果要走，錢是多少

假設一套裝備從一張穿好裝備的角色概念圖切出十件：

| 步驟 | 點數 |
|---|---|
| 分析 | 2 |
| 執行，產出每件的視圖 | 50 |
| 十件各自生成，用 Meshy V6 60 點 | 600 |
| 合計 | **652 點，約 $13** |

16 件掛零件如果分三套外觀去生，大約 2,000 點、$40 上下，Pro 一年的點數吃得下。
但是這個估算有兩個大前提沒驗證過：**原點對不對得上 socket**，見 6.2 節；
還有**切出來的盔甲能不能貼合我們的身體網格**，官方自己寫了
「expect to nudge fits at assembly」，那句話在建築上是致命的，
在角色身上是要手工調的工時。

**還有一條更便宜的路要一起放上來比：**16 件全部是散裝的武器盔甲披風頭盔，
**把它們攤平排成三張格子圖，走現有的 `split_group`，三個任務 90 Meshy 點，約 $1.80。**
那條路做得出東西，只是做不出「和這一套身體風格一致的整套外觀」，
因為每一件是獨立描述的，不是從同一張穿著圖來的。
`docs/Meshy使用說明.md` 第 9.5 節規則一講的正是這個問題：
配色和記憶點跟著科別走不跟著批次走，分批產的同科怪物就對不起來。

所以真正的取捨不是「做得出來或做不出來」，是**「$1.80 換十六件各自為政的裝備」
對上「$40 換三套彼此協調、而且和身體同源的外觀」**。這是使用者要決定的。

### 7.4 四個要先知道的坑

**第一個坑，也是最大的：`base_color_image` 只會找到一張貼圖。**

```python
def base_color_image(obj):
    """從匯入的材質裡找出 albedo 貼圖，找不到回 None"""
    for slot in obj.material_slots:
        ...
                    return link[0].from_node.image
```

它一找到第一張就回傳。Meshy 給的是一整塊網格配一個材質，所以這樣寫沒問題，
`style.py` 的註解也寫得很清楚：「Meshy 的網格只有一個材質槽」。

**AssetHub 的賣點正好是相反的：它給有名字的零件，每個零件可以有自己的貼圖。**
一棟房子如果切成屋頂、牆、門三個零件三張貼圖，`import_glb` 把它們合成一個物件之後
會有三個材質槽，`base_color_image` 只拿第一張，`apply_style` 再把三個槽清掉換成一個。
**結果是屋頂和門的顏色全部變成牆的顏色。**這不會報錯，只會默默錯掉。

兩個解法，選一個：
- 在 AssetHub 端就輸出合併成單一材質單張貼圖的版本，維持和 Meshy 一樣的形狀。
  這樣完全不用改程式，但是它的模組化賣點等於沒用到
- 改 `cleanup.py` 讓它保留每個材質槽各自的貼圖。這要動到 `apply_style`，
  而 `style.py` 現在是「一個物件一個材質」的假設，改動不小

**第二個坑：`import_glb` 的 `join()` 會把零件階層吃掉，但這是要改的東西不是理由。**

`bpy.ops.object.join()` 把所有網格併成一塊。上一版拿這一行去論證零件沒有價值，
那是拿限制證明限制，這一版更正：**`join()` 存在的原因只是 Meshy 從來只給一整塊，
不是因為我們不要零件。**

實際上不用改它也能用，因為 AssetHub 匯出的零件本來就是**一件一個檔**，
不是一個 glb 裡的多個節點。所以正確的接法是把每一件當成獨立的一筆 job 各自跑
`cleanup.py`，`join()` 面對單一網格是無害的。要改的只有 `jobs.json` 的寫法，
一件一筆，不是程式。

真正要改程式的情況只有一種：想拿 AssetHub 的**組合檔**進來再自己拆。
那不必要，直接下載零件就好。

**第三個坑：FBX 進不來。**`import_glb` 寫死用 gltf 匯入器。
四邊形輸出只給 FBX，所以那條路要多寫一個匯入分支。
不過我們 `TOPOLOGY = "triangle"`，四邊形本來就不要，這個坑繞過去就好。

**第四個坑：整條自動化都要重寫。**`batch.py`、`client.py` 和 `config.py` 裡的
`CREDITS` 表全部是照 Meshy 的 API 寫的，端點是 `api.meshy.ai`，
預算檢查靠回傳的 `consumed_credits` 對帳。AssetHub 的 API 完全不一樣。
**乾跑、`--budget` 天花板、送出前再檢查一次付不付得起、事後對帳，這一整套保護都不存在。**

好消息是它有官方 CLI 和 MCP，所以不是只能手工點網頁：

```sh
assethub mesh generate --file ./concept.png --wait --download --out-dir ./out/mesh
assethub mesh download mesh_123 --out-dir ./meshes
```

CLI 的環境變數是 `ASSETHUB_API_KEY`，每一次執行會回傳 execution 物件，
裡面有點數用量。要做成和現在一樣安全的批次工具是可行的，工作量大概是
一個 `art_pipeline/assethub/` 資料夾配一個包 CLI 的 `batch.py`，
`cleanup.py` 之後完全共用。

CLI 說明檔在 https://github.com/AssetHub-inc/assethub-cli

### 7.5 多花的錢換到什麼

**同一次 Meshy 生成，在 AssetHub 要花大約兩倍的錢。**

| | 直接用 Meshy | 走 AssetHub |
|---|---|---|
| Meshy V6 圖生 3D 含貼圖 | 30 Meshy 點 | 60 AssetHub 點 |
| 方案 | Pro 定價 $20 一個月 1,000 點 | Pro 年繳 $192 一年 9,600 點 |
| 每點成本 | $0.020 | $0.020 |
| **一次生成的成本** | **$0.60** | **$1.20** |

每點成本剛好一樣，但是**同一個操作在 AssetHub 記你兩倍的點數**。
換成 Max 或 Studio 方案每點便宜一點，一次生成是 $0.96 和 $0.87，還是比較貴。
Meshy 官網現在還在打五折，價差會更大。

多付的那一倍換到這些東西：

**真的多出來的：**

1. **從穿著圖上拆零件。**分析 2 點加執行 50 點再加每件各自生成。
   **這是它唯一一項我們完全做不到的能力**，見 7.3 節。
   我們的 `split_group` 只切得開攤平擺開的散件，切不開穿在身上的東西
2. **每個零件有自己的 UV 和自己的貼圖。**這是上一條的附帶效果，但它本身就值錢，
   因為自己切零件會讓每一件拖著整組的圖集，見 6.3 節那六個逐位元相同的 2.26 MB
3. **一個訂閱通吃七家模型。**Tripo 3.1、Tripo P1.0、Meshy V6、Rodin Gen-2.5、
   Hunyuan3D 3.1、Hitem3D v2.1、Nano Banana。要比較哪一家做建築比較好的時候，
   不用開七個帳號。實在，但那是採購便利不是技術價值
4. **AI 重生貼圖。**60 點起。**第 5.4 節講的那個值得試的東西**
5. **AI 重拓樸。**25 到 75 點。把生成出來的三角形湯重建成均勻的網格
6. **AI 重展 UV。**15 點。把碎片圖集重新切一次
7. **多視角。**5 點一個視角，讓模型知道背面長什麼樣。Meshy 也有多圖輸入，不算獨有

**對我們沒用或有更便宜替代品的：**

- **重拓樸**：我們有 `cap_polygons` 的 Decimate，零成本，而且保留貼圖。
  AI 重拓樸反而會作廢貼圖，逼你再花 60 點重生
- **重展 UV，整塊不拆的道具**：`style.py` 是照原本的 UV 取樣 albedo，
  明暗由法線和 mpalette 的光向量重算。只要網格和貼圖是配對的，碎不碎不影響畫面。
  我們不手繪貼圖、不平鋪、不重烘，所以整潔的 UV 在這個情境下沒有地方消費。
  **但這句話只限整塊不拆，要拆零件就不成立了，見 6.3 節**
- **零件切割，用在散裝小道具**：`split_group` 一個任務 30 點換六件，
  AssetHub 同樣六件要 412 點。**十四倍價差**，見 7.2 節
- **零件切割，用在模組化建築**：它自己寫「Parts are generated, not carved」，
  組裝要手工微調接縫，那和模組件要精準拼接的前提直接衝突，見 6.4 節
- **綁骨**：50 點，場景道具不需要

**一句話總結第 7 節：對地圖素材，多付的那一層買到的東西我們要嘛用不到、
要嘛已經有便宜十四倍的做法，唯一值得試的是 AI 重生貼圖。
對角色裝備，它有一項真正獨有的能力，那項能力對到一個 16 件全空的洞，
但是要不要走那條路是使用者的決定，這份文件不替他決定。**

---

## 8. 沒能確認的事

這次是純調查，沒有註冊也沒有登入，所以下面這些只能靠別的方法確認。

**排最前面的三條是這一版新增的，而且是零件那條路的關鍵未知數。**

| 沒確認的 | 為什麼沒確認 | 怎麼確認 |
|---|---|---|
| **零件的原點在哪裡** | 官方四篇部落格和 CLI 說明檔全部沒提 pivot 或 origin。6.2 節那段「八成是身體座標系」是推論 | 切一次零件下載回來，在 Blender 裡量每一件的原點位置。**這一項不確認就不能說它能直接掛上 socket** |
| **零件有沒有名字，名字是什麼** | 部落格說是「named parts」，但是沒有列命名規則，也沒有範例檔名 | 同上，看解開的 ZIP 裡檔名長什麼樣 |
| **切出來的盔甲貼不貼合我們的身體網格** | 官方自己寫「expect to nudge fits at assembly」，但沒說要調多少 | 要真的切一套穿著圖，掛到 `characters_real` 的身體上看接縫 |
| **零件切割對非角色主體有沒有用** | 官方範例、教學、社群展示全部是角色，建築零範例 | 拿一張房子概念圖切一次看它辨識出什麼零件 |
| **下載介面到底給哪些格式** | 官方沒有任何一頁列匯出格式，GLB 和 FBX 是從四篇部落格拼出來的 | 註冊免費帳號生一個最便宜的東西，看下載按鈕的選項。免費方案只能拿來測格式，生出來的東西不能進遊戲 |
| **貼圖到底是幾張、通道怎麼分** | 部落格只說「full PBR material set」，沒有列檔名 | 同上，下載一包解開來看 |
| **公開 API 文件** | `app.assethub.io/docs/api` 要登入，回 307 轉址 | 註冊後看，或是裝 CLI 跑 `assethub api search` |
| **CLI 下載下來的目錄結構** | 說明檔只寫會產生 `manifest.json`，沒有範例 | 註冊後 `assethub mesh download` 跑一次 |
| **免費方案卡片上「Commercial use」和問答矛盾** | 兩處寫法不同，只能以條款為準 | 寫信到 info@assethub.studio 要一句白紙黑字。**在拿到回覆之前一律當成免費不能商用** |
| **點數沒用完會不會累積到下個月** | 官方只寫 replenished，沒寫 roll over | 問客服，或是訂一個月自己看 |
| **Max 和 Studio 的月繳價** | 官方只明講 Pro 月繳 $20，另外兩個是照兩成比例推的 | 在價目頁把切換鈕按到 Monthly |
| **場景建築的實際品質** | 官方零範例，社群展示全是角色 | 最小測試：Tripo 3.1 最低檔 25 點生一個市集攤位，照現有 `jobs.json` 的 `market_stall` 那一筆描述。加 60 點重生貼圖是 85 點，約 $1.70 |
| **AI 重生貼圖能不能解掉色塊分不開的問題** | 這是第 5.4 節說唯一值得試的那一件，沒人做過 | 和上一條同一次測試。判斷方法照 `docs/Meshy使用說明.md` 第 9.5 節規則二，在晨曦鎮的實際底色上看，不要用綠底聯絡表 |
| **多零件模型進 `cleanup.py` 會怎樣** | 第 7.4 節第一個坑是讀程式推出來的，沒有實測 | 拿一個真的有多個材質的 glb 跑一次 `cleanup.py`，看 `has_base_color` 和輸出的顏色對不對 |
| **上游七家模型各自的條款** | 第 5 條第 2 項要我們自己去看，這次只看了 AssetHub 和 Meshy | 真的要用之前把 Tripo、Hunyuan、Rodin、Hitem3D、Nano Banana 的條款各看一次 |
| **退訂之後先前產出的授權** | 條款沒有終止後效力條款，第 3.6 節是推論 | 寫信問，要書面回覆。**同時不管答案是什麼，每一件都要當天下載進版本庫** |

### 建議的下一步

不要先買年費。順序是：

1. 寫信問兩件事：免費方案能不能商用的矛盾，還有退訂之後先前產出能不能繼續用
2. 註冊免費帳號，用免費點數**只做一件事**：生一個東西下載下來，確認格式和貼圖張數。
   **這一份不能進遊戲**
3. 訂一個月 Pro $20 做兩個測試，一次把兩題答完：
   - **地圖那一題**：85 點測市集攤位，Tripo 3.1 最低檔 25 點加重生貼圖 60 點，
     和現有的 Meshy 版並排比。判斷方法照 `docs/Meshy使用說明.md` 第 9.5 節規則二，
     在晨曦鎮的實際底色上看，不要用綠底聯絡表
   - **零件那一題**：切一套穿著裝備的角色，652 點左右，
     量每一件的原點、看檔名、把盔甲掛到 `characters_real` 的身體上看接縫。
     這一次測試會同時答掉第 8 節排最前面那三條未知數
4. 兩個測試都不過就退訂，繼續走現有的 Meshy 管線

**一個月 $20 換掉整份文件裡所有「推論」和「未確認」，這個價錢很便宜。**
但是要先想清楚：**零件那一題是角色的題目，不是地圖的題目。**
使用者這次問的是地圖素材，角色那條路他另外決定，
所以第 3 步的第二個測試要不要做，等他先決定角色走哪條路再說。
