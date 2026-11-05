# 自動比價系統

每天 09:30、15:00、21:00 自動到 momo、PChome 24h、Yahoo購物中心、Yahoo拍賣、露天拍賣、誠品、金石堂、BigGo（含蝦皮、iOPEN Mall、旋轉拍賣、博客來、讀冊）搜尋你追蹤的商品，價格符合條件時用 Telegram 通知你，並把價格歷史畫成走勢圖網頁。

全部跑在 GitHub 上，**電腦不用開著**，也不用付費。

---

## 什麼時候會收到通知

依商品的類別，用不同的規則判斷：

| 類別 | 通知條件 |
|---|---|
| 樂高 | 低於原價 7 折（不含 7 折）→「甜蜜點」；6.5 折以下 →「超甜價」。只算正版、全新或二手未拆（盒損可以），疑似非正版和已拆封的不抓 |
| 漫畫 | 原價 85 折以下（含）→「好價」；電子書、狀況不明的二手書不抓 |
| 保養品 | 前 14 天只記錄。之後比過去 30 天的一般價格便宜 15% 以上 →「特價」 |
| 3C、電器 | 前 14 天只記錄。之後比過去 30 天的一般價格便宜 10% 以上 →「特價」 |

所有類別共通的通知：

| 情況 | 通知內容 |
|---|---|
| 第一次追蹤某個商品 | 「開始追蹤」，附上目前最低價和折數（用來確認設定成功） |
| 現價比過去所有紀錄都低 | 「歷史新低」，就算沒達到上面的折數也會通知 |
| 有設定目標價，且價格達到 | 「達到目標價」 |
| 某個網站連續一天都抓不到資料 | 「提醒」，代表網站可能改版，需要修程式 |

同一個等級不會重複通知。例如通知過「甜蜜點」之後，要再降到「超甜價」才會再通知；如果價格漲回 7 折以上又降下來，會重新通知。

規則的數字（7 折、15% 等）都寫在 `products.yaml` 的 `categories` 區塊，可以自己改。

---

## 安裝步驟（第一次設定，約 20 分鐘）

### 第 1 步：建立 Telegram 機器人

1. 手機打開 Telegram，搜尋 **@BotFather**（有藍色勾勾的那個），按「開始」
2. 輸入 `/newbot` 送出
3. 它會問機器人名字，隨便取，例如 `我的比價小幫手`
4. 再問帳號名稱，必須是英文並以 `bot` 結尾，例如 `myprice2026_bot`
5. 成功後會給你一串像這樣的文字，這就是 **Bot Token**，先複製起來：
   ```
   7712345678:AAH3xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   這串 Token 等於機器人的密碼，不要給別人看
6. 點 BotFather 訊息裡的機器人連結（`t.me/你的機器人帳號`），按「開始」，再隨便傳一句話給它，例如「你好」
7. 用電腦瀏覽器打開下面網址（把 `你的Token` 換成第 5 步那串）：
   ```
   https://api.telegram.org/bot你的Token/getUpdates
   ```
8. 畫面會出現一堆文字，找到 `"chat":{"id":` 後面的數字，例如 `"chat":{"id":123456789`，這個數字就是 **Chat ID**，也複製起來
   （如果畫面只有 `{"ok":true,"result":[]}`，回到 Telegram 再傳一句話給機器人，然後重新整理網頁）

### 第 2 步：在 GitHub 建立專案

1. 登入 [github.com](https://github.com)
2. 右上角「**+**」→「**New repository**」
3. **Repository name** 填 `price-tracker`
4. 選 **Public**（公開；這樣走勢圖網頁才能免費使用）
5. 其他都不用勾，按最下面的「**Create repository**」

### 第 3 步：上傳程式檔案

1. 在剛建好的專案頁面，點「**uploading an existing file**」這個連結
2. 把 `price-tracker` 資料夾**裡面的所有東西**（不是資料夾本身）全選，拖曳到網頁上
   要包含 `.github` 這個資料夾。Windows 如果看不到它，在檔案總管上方「檢視」→ 勾選「隱藏的項目」
3. 等上傳完成，按最下面綠色的「**Commit changes**」
4. 確認專案首頁看得到 `.github`、`pricewatch`、`docs`、`products.yaml` 這幾個項目

### 第 4 步：把 Telegram 資料存進 GitHub（加密保存）

1. 專案頁面上方點「**Settings**」（齒輪圖示）
2. 左邊選單「**Secrets and variables**」→「**Actions**」
3. 按「**New repository secret**」
   - Name 填 `TELEGRAM_BOT_TOKEN`
   - Secret 貼上第 1 步的 Bot Token
   - 按「Add secret」
4. 再按一次「**New repository secret**」
   - Name 填 `TELEGRAM_CHAT_ID`
   - Secret 貼上第 1 步的 Chat ID
   - 按「Add secret」

存進去之後，任何人（包括你自己）都看不到內容，只有程式執行時讀得到。

### 第 5 步：允許程式儲存價格紀錄

1. 一樣在「**Settings**」，左邊選單「**Actions**」→「**General**」
2. 拉到最下面「**Workflow permissions**」
3. 選「**Read and write permissions**」
4. 按「**Save**」

### 第 6 步：開啟價格走勢網頁

1. 「**Settings**」→ 左邊選單「**Pages**」
2. 「**Source**」選「**Deploy from a branch**」
3. 「**Branch**」選 `main`，旁邊資料夾選 `/docs`，按「**Save**」
4. 等 1～2 分鐘重新整理，上方會出現網址，例如 `https://你的帳號.github.io/price-tracker/`，這就是走勢圖網頁

### 第 7 步：手動跑第一次

1. 專案上方點「**Actions**」
2. 左邊點「**定期比價**」
3. 右邊按「**Run workflow**」→ 再按綠色的「**Run workflow**」
4. 等 1～2 分鐘，出現綠色勾勾就是成功，Telegram 會收到「開始追蹤」的訊息
5. 如果出現紅色叉叉，點進去把錯誤畫面截圖給 Claude

之後每天台灣時間 09:30、15:00、21:00 會自動執行。GitHub 的排程常常會晚 5～30 分鐘才開始跑，這是正常的。

想改執行時間，就改 `.github/workflows/check-prices.yml` 裡的 `cron` 那幾行（裡面有註解說明怎麼換算）。

---

## 臨時比價（馬上查一次最低價）

想買的東西不用加進追蹤清單，也可以馬上查：

1. 打開 https://github.com/liebe9955chn/price-tracker/actions/workflows/quick-search.yml
   （手機可以用 GitHub App：專案 → Actions → 臨時比價）
2. 按右邊「**Run workflow**」，填入：
   - **要查的商品**：例如 `被討厭的勇氣`，書也可以填 ISBN（書背條碼那串 978 開頭的數字）
   - **標題一定要有的字**：可以不填。結果太雜時再填，例如 `被討厭的勇氣 阿德勒`
   - **要排除的字**：可以不填。例如 `二部曲 套書`
   - **二手也要看**：要看二手就打勾
3. 按綠色的「**Run workflow**」，2 到 3 分鐘後 Telegram 會收到結果

結果分成兩區：
- **商城、書店**：PChome、momo、博客來、誠品等，都是全新品
- **拍賣、個人賣場**：蝦皮、露天、Yahoo拍賣等，價格常常比較低，但可能是二手，要點進去確認

也可以直接在 Claude 問「幫我查 XXX 最低價」。

---

## 新增或修改追蹤的商品

1. 在 GitHub 專案頁面點 `products.yaml`
2. 點右上角的**鉛筆圖示**（Edit this file）
3. 照檔案裡的說明和範例，複製一段商品設定貼在最後面，改成新商品的內容
4. 按右上角「**Commit changes...**」→ 再按一次「**Commit changes**」
5. 想馬上看結果，就到「Actions」手動執行一次（第 7 步）

### 設定範例

```yaml
  - name: LEGO 77059 動物森友會 豆狸&粒狸 悠閒散步
    category: 樂高
    keywords: ["樂高 77059", "LEGO 77059"]
    must_include: ["77059"]
    original_price: 2299

  - name: 葬送的芙莉蓮 14
    category: 漫畫
    keywords: ["葬送的芙莉蓮 14"]
    must_include: ["芙莉蓮", "14"]
    exclude: ["全套", "1-13"]
    original_price: 110

  - name: Panasonic 16公升除濕機 F-Y32GH
    category: 3C
    keywords: ["Panasonic F-Y32GH", "國際牌 F-Y32GH"]
    must_include: ["Y32GH"]
    min_price: 5000
    max_price: 20000
```

### 設定小技巧

- **must_include** 放型號或最能代表這個商品的字。型號最準，例如除濕機的 `Y32GH`、樂高的 `40817`
- 搜到很多不相關的東西，就在 **exclude** 加排除字
- 樂高和漫畫有填原價的話，會自動忽略低於原價 4 成（漫畫 3 成）的價格，擋掉零件和假價格。保養品、3C 沒有原價，建議自己填 **min_price**
- 每一行前面的空白要對齊範例，不能用 Tab 鍵。存檔後如果 Actions 出現紅色叉叉，多半是空白沒對齊

---

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `products.yaml` | 追蹤的商品清單，**平常只需要改這個** |
| `pricewatch/` | 程式本體 |
| `data/history.csv` | 每次抓到的各網站最低價紀錄（可以用 Excel 打開） |
| `data/state.json` | 歷史最低價和通知狀態 |
| `docs/` | 走勢圖網頁 |
| `.github/workflows/check-prices.yml` | 排程設定（每天 09:30、15:00、21:00） |

## 費用

- GitHub Actions：公開專案免費，沒有次數限制
- GitHub Pages：公開專案免費
- Telegram：免費
