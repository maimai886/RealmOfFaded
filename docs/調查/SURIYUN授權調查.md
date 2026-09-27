# SURIYUN 授權調查

調查日期 2026-09-17。**沒有購買、沒有下載、沒有註冊帳號、沒有留任何個人資料**，只看公開的商品頁和授權頁。

這份只回答一件事：買 SURIYUN 的素材之後，能不能合法用在 Sproutia。主查 Fab，也就是 Epic 的素材市集。
美術方向要走像素還是 3D 不在這份的範圍內。

---

## 1. 一句話結論

**授權上可以用。**Fab 的標準授權明文允許在任何相容工具裡使用，不限 Unreal，商用、修改、重綁骨架、重新算圖、用在多個產品、一個人做不用買席次、不用標註來源，全部沒問題。

**最大的風險不是授權，是檔案格式。**SURIYUN 在 Fab 上的 103 個商品裡，**只有 22 個附 fbx**，71 個只給 Unreal 的 .uasset。
.uasset 在 Godot 打不開，授權再寬鬆也用不了。**下單前一定要先看商品頁的「包含格式」有沒有 fbx。**

授權本身唯一的灰色地帶是第 2.3 節那條：條款要求我們「限制玩家從遊戲裡取出素材」，
我們是客戶端帶著模型跑的 MMO，Godot 的 .pck 很好解，而條款沒有定義要做到什麼程度才算限制。

---

## 2. 逐條的授權發現

SURIYUN 官網 https://www.suriyun.com/ **不自售**，只是型錄，導去 Unity Asset Store、Fab、Unity 中國站三個地方，
官網上沒有任何授權條款頁，只留 contact@suriyun.com。**沒有「跳過平台直接跟作者買」這條路。**

以下引用的條款全部出自 Fab End User License Agreement，https://www.fab.com/eula ，最後更新 2024-10-01。

### 2.1 Fab 的授權種類

Fab 只有兩種授權，SURIYUN 全部走標準授權。來源 https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab ：

> Fab offers the following license types: Creative Commons Attribution (CC-BY) (Free) / Standard (Free or For Sale)

CC-BY 只能用在免費商品，SURIYUN 沒有。標準授權分三階，差別在「你的收入」和「拿到什麼檔案」，**不在你能做什麼**。
Fab 授權頁的摘要原文：

> 两种定价等级（个人版和专业版）所授予您的权利范围相同

階級的門檻寫在 EULA 第 2(a) 條：

> You are only eligible for a Personal - Reference Only tier or Personal tier if, at the time of the Transaction you, together with any controlling entity and other entities under common control with you, have not generated more than $100,000 USD in gross revenue from your commercial activity in the digital content industry in the last 12 months.

同一條也寫，買錯階級之後被要求就要補差價。**我們現在適用 Personal。**
過了門檻之後不用回頭補升級，摘要原文：「如果您在购买后收入超过阈值，无需从个人版升级到专业版」。

第三階 Personal - Reference Only 要避開，第 2(d)(i) 條：

> Standard License under a Personal - Reference Only tier: you may access the Content as a reference asset only

拿到的是參照檔不是原始檔，只有 UEFN 用得到。**買的時候要確認選的是 Personal 不是 Personal - Reference Only。**

### 2.2 能不能用在非 Unreal 的引擎

**可以，而且 Fab 把這件事寫在授權摘要的第一層。**

授權頁的摘要「您可以」清單裡直接列著：

> 通过任何兼容工具使用资源（使用不限于 Unreal Engine）

摘要自己聲明不具法律約束力，所以再看正文。第 3(a) 條的授權本文：

> A "Standard License" grants you a non-exclusive and non-transferable license to privately use, reproduce, display, perform, and modify the Content in accordance with the terms of this Agreement. This means that as long as you are not violating this Agreement ... you can privately use the Content however you want under a Standard License.

**整份 EULA 沒有任何一條把使用範圍綁在 Unreal Engine 上。**限制寫在第 6 節，全部是關於「不能拿去做什麼」，沒有一條關於「不能用什麼工具做」。

有一條和引擎有關的要確認，第 6(a) 條禁止和傳染性授權混用：

> you may not combine Content under a Standard License with code or content that is licensed under any of the following licenses: GNU General Public License (GPL), Lesser GPL (LGPL) (unless you are merely dynamically linking a shared library), or Creative Commons Attribution-ShareAlike License.

**Godot 是 MIT 不是 GPL，這條踩不到。**但它會擋到 CC-BY-SA 的素材，
`docs/調查/像素素材採購選項.md` 裡的 LPC 系列就是 CC-BY-SA，那批東西不要和 Fab 買來的放在同一個專案。

**真正的門檻是檔案格式不是授權。**Fab 商品頁右欄有一列「包含格式」，SURIYUN 的商品分三種：

| 格式組合 | 商品數 | Godot 能不能用 |
|---|---|---|
| unreal-engine 只有這個 | 71 | **不能**，.uasset 在 Godot 打不開 |
| unreal-engine + fbx | 16 | 可以，直接拿 fbx |
| unreal-engine + unity + fbx | 6 | 可以 |
| unreal-engine + unity | 9 | 大概可以，.unitypackage 是壓縮檔，裡面通常是原封的 fbx 和 png，但沒有實際驗證過 |
| unity 只有這個 | 1 | 同上 |

第 2(d) 條寫得很清楚，拿到的是什麼就是什麼：

> Source assets are files that contain full copies of the Content in Unreal Engine format and possibly other formats (as listed), which can be modified and incorporated into your projects.

「possibly other formats (as listed)」就是商品頁列的那些。**沒列 fbx 就沒有 fbx，不能假設有。**

### 2.3 MMO 客戶端會被玩家挖出素材，有沒有限制

**有，這是整份條款裡唯一對我們真正棘手的一條。**第 4(c) 條原文：

> you may Distribute a Project that incorporates Content as an included dependency to end users. When you make such a Distribution, you may, however, only authorize end users to make use of Content solely as incorporated in the Project in object code and you must restrict end users from extracting or otherwise using Content outside of the Project.

前半段明確允許我們把素材包進遊戲發給玩家，包括線上遊戲，同一條後面還寫：

> you may Distribute software applications (such as video games) that include Content to the general public, whether directly by you or through a distributor or publisher.

**問題在「you must restrict end users from extracting」這句。**
Godot 匯出的 .pck 只要沒加密，任何人用公開工具幾分鐘就能把模型和貼圖倒出來。
條款沒有定義要做到什麼程度才算 restrict，也沒有寫要用什麼技術手段。

實務上的對策是開 Godot 內建的 .pck 加密，金鑰編進執行檔，擋得住隨手翻的人、擋不住認真逆向的人。
**這是普遍做法，但沒有條文背書**，要怎麼確認見第 3 節。

另外兩條和 MMO 有關的，我們現在都沒踩到：

**素材不能是產品主體**，第 6(b)(ii) 條：

> sell, rent, lease, or transfer the Content on a "stand-alone basis" (this means, for example, Projects you Distribute must reasonably add value beyond the value of the Content and the Content must be merely a component of the Project and not the primary focus of the Project)

我們是一整套有伺服器、戰鬥、經濟系統的 MMO，素材只是角色和怪物，沒問題。

**不能做讓玩家自己捏內容的系統**，第 6(b)(iii) 條：

> allow any third party to incorporate Content into their own products, services, or other projects (this means, for example, that you may not make Content available in world- or level-editing tools or templates or other modeling tools that allow works to be exported)

以後要做玩家自訂地圖或自訂外觀編輯器，買來的素材不能放進去給玩家用。現在的規劃沒有這種東西。

### 2.4 能不能修改、重綁骨架、重新算圖

**全部可以，而且改出來的東西是我們的。**

第 3(a) 條的授權本文就包含 modify，摘要那行是「修改和调整资源，以便将其纳入您的项目」。
第 6 節的限制清單裡**沒有任何一條禁止衍生作品**，唯一和改動有關的是 6(b)(i) 禁止逆向工程程式碼，我們買的是模型不是程式。

所有權寫在第 2 節最後一段：

> Who Owns What. As between you and us, you own all rights, other than rights in the Content, in anything you make with the Content under this agreement and we or our licensors own all title, ownership rights, and intellectual property rights in the Content.

**改比例、換貼圖、重新綁骨架、重新算圖、算成精靈圖集，全部在授權範圍內，衍生作品的權利歸我們。**
這一點和 `docs/調查/素材採購選項.md` 裡查到的 GameDev Market 相反，那邊明文寫衍生作品智財歸賣方。

### 2.5 單一產品還是多個產品，團隊要不要買多份

**沒有單一產品限制，整份 EULA 沒有任何數量上限。**
第 4(a) 條講 Project 的時候用的是複數「you develop projects」，第 3(a) 條授權本文也沒有綁定任何特定產品。
這和 `docs/調查/像素素材採購選項.md` 裡 Mana Seed 明文「a SINGLE PRODUCT」的做法相反。

**團隊不用各買一份。**第 5(a) 條：

> you may not Distribute Content on a standalone basis to third parties except to your collaborators (either directly or through a third-party repository) who are utilizing the Content in good faith to develop a Project with you or on your behalf. This means, for example, that you may share Content with your employees, affiliates, and contractors in a private online repository while you work on a Project together.

條件是那些人不能再往外散布，而且專案結束要刪掉，同一條：

> Those collaborators you share Content with are not permitted to further Distribute the Content (including as incorporated in a Project) and must delete the Content once it is no longer needed

per-seat 只適用於程式外掛，第 2(e) 條：

> Code plugins that are being offered on the Epic Marketplace, including Unreal Engine Plugins and Unity Plugins ("Plugins"), are offered to you on a per-seat basis and may only be used by the number of users that you have purchased licenses for.

**SURIYUN 賣的 103 個商品全部是 3D 分類，不是 Plugin，不用算席次。**

### 2.6 要不要標註來源

**不用。**授權頁摘要的「其他注意事项」原文：

> 无需向您获取 Fab 资源的发布者致谢

EULA 正文也沒有任何 attribution 或 credit 的要求。
SURIYUN 商品頁只有一句軟性的請求「If you please, kindly take a few minutes to leave us rating or review」，那不是條款。

### 2.7 作者下架之後還能不能用

**授權還在，但檔案可能拿不回來，所以買了當天就要自己備份。**

第 3(b) 條：

> we do not guarantee that you will be able to always re-download or re-access Content from the Epic Marketplace. Reasons for removal may include take-down due to intellectual property infringement or other legal violation, seller violation of terms, and obsolescence. We encourage you to backup Content you have purchased.

授權本身不會因為下架而消失，第 7(a) 條給了明確保障：

> Any Content you acquired (whether free or paid) prior to the modified terms will remain governed by the license terms applicable at the time when you acquired the Content.

同一條也寫，Fab 改條款我們不一定要接受：

> If we make changes to this Agreement, you are not required to accept the amended version. Until you accept the amended version, this Agreement will continue to apply.

代價是不接受新版就不能再買新東西、不能更新已買的東西。

**這一條比 Unity 那邊乾淨很多**，Unity 商店的 Terms 第 7.4 條寫，Unity 哪天決定收掉 Asset Store，
「all legal rights granted to you under these Terms will immediately terminate」，和 EULA 寫的永久授權互相打架。

退款走 Fab Support，政策見 https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab 。

### 2.8 AI 條款

第 6(b)(vii) 和第 16(l) 條，限制對象是被標成 NoAI 的商品：

> you may not use NoAI Content (i) in datasets utilized by Generative AI Programs; (ii) in the development of Generative AI Programs; or (iii) as training inputs to Generative AI Programs.

**這個標示逐個商品不一樣**，在商品頁右欄的「允许使用 AI」那一列。實際查到的：
Little Heroes Pack 是「否」也就是 NoAI，Monsters Forest Pack 3 是「是」。

管的只有拿素材去訓練或生成，不管我們在 Blender 裡算圖、換貼圖、重綁骨架。
第 16(l)(ii) 條還特別寫了 AI 放大這類「solely operate on the Content」的功能不算生成式 AI。

**這和 `docs/調查/像素素材採購選項.md` 第 5 節 Mana Seed 那條有本質差別**：
Mana Seed 管的是整個專案不准有 AI 產出物，Fab 管的只有素材本身不能餵 AI。
我們專案裡有 AI 產的材質和 AI 寫的程式碼，對 Fab 這邊**不構成問題**。
要守的只有一條：不要把買來的模型或貼圖丟進任何生成式 AI 工具，包括 img2img、訓 LoRA、當 Meshy 的參考圖。

### 2.9 Unity Asset Store 那邊的差別，一句話帶過

同一批包在 Unity Asset Store 也有賣，走的是 Standard Unity Asset Store EULA、License type 是 Single Entity，
**用在 Godot 一樣可以**，Unity 有官方支援文件寫「Unity Asset Store assets are not restricted to Unity projects」，
來源 https://support.unity.com/hc/en-us/articles/34387186019988-Can-I-use-assets-from-the-Asset-Store-with-other-engines 。

三個差別：Unity 只有單一價沒有分階，換算下來和 Fab 的 Personal 差不多；
Unity 的 EULA 第 2.4 條規定外包廠商要自己再買一份，Fab 允許直接分享給協作者；
Unity 商品頁完全不寫檔案格式，只寫 .unitypackage 和檔案大小，Fab 會明列有沒有 fbx。
**綜合起來建議走 Fab。**

---

## 3. 沒能確認的事

| 不確定的事 | 為什麼重要 | 怎麼確認 |
|---|---|---|
| **「must restrict end users from extracting」要做到什麼程度才算數** | 本案最大的授權風險。我們是客戶端帶模型的 MMO，Godot 的 .pck 很好解 | 寫信問 legal@epicgames.com，問「將素材封裝在加密的遊戲資料包中，是否滿足 Section 4(c) 的 restrict 要求」，把回覆存檔 |
| **只給 unity 格式那 10 個包，.unitypackage 裡到底是不是原封的 fbx 和 png** | Cute Slime 全系列都在這一類，沒有 fbx | 寫信問 contact@suriyun.com，問能不能提供 fbx 版本。或者只買明列 fbx 的那 22 個 |
| **各包的動作清單和數量** | Fab 商品頁的技術細節欄位寫法不一致，有些有寫 Number of Animations 有些沒有 | 買之前在商品頁的 technicalDetails 欄位逐一看，沒寫的就寫信問 |
| **各包的 NoAI 標示** | 逐個商品不一樣，只實際查了兩個 | 下單前逐一看商品頁右欄的「允许使用 AI」，並且截圖 |
| **Fab 版和 Unity 版是不是同一批模型** | 兩邊角色命名不一樣，Little Heroes 在 Unity 上叫 Red Mage、Castle Guard、Archbishop，在 Fab 上叫 Mistic、Carmel、Holden、Landon | 寫信問 contact@suriyun.com |

**共通的做法**：買之前把每個商品頁連同授權欄位、格式欄位、AI 欄位一起截圖，存進 `art_source/licenses/`。
Fab 第 7(a) 條只保障「購買當時」的條款，沒有當時的證據等於沒有保障。

---

## 4. 目前的包和價錢

Fab 上共 **103 個商品，全部是 3D**。賣場 https://www.fab.com/sellers/SURIYUN 。
價錢是 2026-09-17 查到的美金未稅價，格式是 Personal / Professional，Professional 大約是三倍。

### 使用者 2026-09-16 看過的三個

| 包名 | Fab 價錢 | 含 fbx | 內容 |
|---|---|---|---|
| Little Heroes Pack | $79.99 / $239.99 | **有** | 七個角色，臉、皮膚、頭髮、衣服貼圖分開所以好換色。Unity 版寫 32 個原地動作。商品頁註明 UE 版不含 Unity 的腳本和 Toon 著色器 |
| Cute Slime | $29.99 / $89.99 | **沒有**，只有 unreal-engine + unity | 史萊姆。同系列 Cute Slime 2 到 5 各 $28.99，也都沒有 fbx |
| Monsters Forest Pack 3 | $39.99 / $119.99 | **有** | 34 隻森林系怪物 |

商品頁：
- https://www.fab.com/listings/fbbb0858-de4b-4710-a024-b62045d339bb
- https://www.fab.com/listings/3e314b6a-880d-4e5b-945a-05d7be1de828

### 附 fbx 的 22 個包，也就是 Godot 能直接用的全部

| 包名 | Personal / Professional |
|---|---|
| Little Heroes Pack | $79.99 / $239.99 |
| Monsters Forest Pack | $39.99 / $119.99 |
| Monsters Forest Pack 2 | $39.99 / $119.99 |
| Monsters Forest Pack 3 | $39.99 / $119.99 |
| Monsters Darkness Pack | $29.99 / $89.99 |
| Monsters Darkness Pack 2 | $39.99 / $119.99 |
| Monsters Fire Pack | $29.99 / $89.99 |
| Monsters Fire Pack 2 | $34.99 / $104.99 |
| Monsters Fire Pack 3 | $39.99 / $119.99 |
| Monsters Desert Pack | $39.99 / $119.99 |
| Monsters Desert Pack 2 | $39.99 / $119.99 |
| Monsters Water Pack | $29.99 / $89.99 |
| Monsters Holy Pack | $24.99 / $74.99 |
| Monsters Pyramid Pack | $29.99 / $89.99 |
| Yippy Kawaii | $29.99 / $89.99 |
| Yippy Kawaii 2 | $29.99 / $89.99 |
| Pspsps Cat | $29.99 / $89.99 |
| Pspsps Dog | $29.99 / $89.99 |
| Pspsps Rabbit | $29.99 / $89.99 |
| Pspsps Bear | $29.99 / $89.99 |
| Pspsps Pig | $29.99 / $89.99 |
| Pspsps Monkey | $29.99 / $89.99 |

**怪物系列十四個包全部有 fbx，這是對我們最有用的一件事。**

### 沒有 fbx 的重要包，買了在 Godot 用不了

| 包名 | Personal / Professional | 格式 |
|---|---|---|
| MEGA Monsters Pack | $119.99 / $349.99 | 只有 unreal-engine |
| MEGA Cute Pet Zoo | $149.99 / $449.99 | 只有 unreal-engine |
| Mega Tiny Dragon | $139.99 / $424.99 | 只有 unreal-engine |
| Monsters Ice Pack | $39.99 / $119.99 | 只有 unreal-engine |
| Cute Goblin | $29.99 / $86.99 | 只有 unreal-engine |
| Anime Girls Pack | $599.99 / $1499.99 | 只有 unity |
| Cute Slime 1 到 5 | $28.99 到 $29.99 | unreal-engine + unity |
| Tiny Dino 1 到 3 | $32.99 / $99.99 | unreal-engine + unity |

**三個 MEGA 整合包全部沒有 fbx**，想靠買大包一次到位這條路在 Godot 走不通，只能一包一包買附 fbx 的。

### 時機

官網首頁 2026-09-17 掛著「LAUNCH SALE - 50% OFF，Coming Soon — Launching September 21th」，
有新品要上而且會跑五折。**要買的話等 9 月 21 日之後再看一次價錢。**

---

## 5. 一句話的行動建議

在 Fab 買，選 Personal 階，**只買商品頁「包含格式」有列 fbx 的那 22 個**，
下單前把商品頁連同授權、格式、AI 三個欄位截圖存檔，買到手立刻自己備份一份，
客戶端匯出時開 Godot 的 .pck 加密，這樣第 2.3 節那條「restrict end users from extracting」才有東西可以主張。
