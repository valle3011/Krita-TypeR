# -*- coding: utf-8 -*-
"""Release notes in the languages the readers of this project actually need.

    python tools/release_i18n.py --check    # every version translated and current?
    python tools/release_i18n.py --stamp    # record the English each one was made from

The plugin itself speaks English and German, because that is what its author
and the people around them use. A release page is read by strangers, and the
people who typeset manga are largely not German: a German typesetter reads
English anyway, so a German column costs space without reaching anyone the
English does not already reach. The notes are therefore English, Japanese and
Simplified Chinese.

**UI labels stay in English** inside the translated text - `Fonts`, `Setup`,
`Batch`, `Preview:`, `TextShapR`. The plugin's own interface is only English or
German, so a translated label would be one the reader cannot find anywhere in
the program: worse than leaving it untranslated.

English lives in `typer_kr/whatsnew.py` with the plugin, since the docker shows
it after an update. Only the translations live here, keyed by version, each
stamped with a fingerprint of the English it was made from - so an English line
that is edited after being translated is caught instead of quietly leaving a
translation that says something else.
"""
import argparse
import hashlib
import importlib.util
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHATSNEW = os.path.join(ROOT, "TypeR-Krita", "typer_kr", "whatsnew.py")
SELF = os.path.abspath(__file__)

#: the order the sections appear in, and the heading each gets. English first
#: because it is the one language every reader here is likely to have.
SECTIONS = [
    ("en", "What's new"),
    ("ja", "新着情報"),
    ("zh", "更新内容"),
]

#: version -> {lang: [line, ...]}. One entry per English line, in the same
#: order, so the two can be read side by side.
NOTES = {
    "1.22": {
        "ja": [
            "Giongo タブ（描き文字）は今回大きく増えましたが、"
            "完成というより「使ってみて、壊れたら教えてください」の段"
            "階です。粗さは残っていて、とくに Liquify はそう"
            "です。ブラシは書いてあるとおりに動きますが大振りで、強め"
            "に引けば語をそっと押すのではなく塗りつぶしてしまいます。"
            "筆圧もスムージングも、ドラッグ中の取り消しもありません。"
            "ここでの操作はすべてCtrl+Z で戻せますし、挿入する"
            "までページには何も起きません。",
            "文字に手を入れられるようになりました。プレビューの上に四"
            "つの道具が並びます。文字を動かす、ブラシで押し動かす（L"
            "iquify）、輪郭の節点をつかむ、一部を消す。手を入れ"
            "た文字も配置・パス・文字ごとの移動にそのまま付いてきます"
            "し、取り消し一回でひと筆まるごと戻ります。",
            "自作のレタリングを書体として使えます。画像・フォルダー・"
            "ZIP を読み込ませると——ファイル名がその文字です（ド"
            ".png は ド）——一度だけ輪郭に起こされ、以後はほか"
            "の文字と同じように、塗りもフチも効いた形で描かれます。",
            "よく使う擬音を 65 語おさめた辞書から選べます。カナ・"
            "読み・意味が入り、ドイツ語と英語で検索でき、選ぶとその音"
            "に合う見た目も一緒に入ります。",
            "見た目の追加：効果の脇に添える小さな文字（描いた ドカー"
            "ン の下の小さな「BOOM」）、ア゛ や ン゛ のための"
            "濁点ボタン、ネガ、線だけ／線を網点にする塗り、三種類の手"
            "によるノイズ線、そして装飾——集中線・破片・きらめき・し"
            "ぶき。",
            "パネルでの取り消しとやり直しが Ctrl+Z と Ctr"
            "l+Y に付き、変更はどれも一手になりました。文字を打っ"
            "ている間はそのキーは入力欄のものです。",
            "保存：レイヤーごとの PNG をまとめた ZIP（同じ画"
            "面サイズなので重ねれば元に戻ります）、Krita 自身が"
            "書き出す PSD、PNG と ZIP の 1〜4 倍の大"
            "きさ。インストールしていないフォントファイルも手で読み込"
            "めますし、フォントそのもので見せる一覧もあります。",
            "タブがかなり速くなりました。太らせとフチ二本のある一枚は"
            " 1352 ミリ秒かかっていたのが 33 ミリ秒に、文字"
            "のドラッグは一歩 23 ミリ秒が2 ミリ秒になりました。"
            "太らせとフチは同じ処理を二度やっていたこと、そして文字の"
            "形は置き場所に左右されないこと——どちらも毎秒六十回一か"
            "ら作り直していました。",
            "別ウィンドウに出すと、描き文字が左側いっぱいに入り、設定"
            "がその横に並びます。ウィンドウはまた画面に収まります。以"
            "前は 1080 px より高く、小さくもできず、下端がデ"
            "スクトップの外に出ていました。",
        ],
        "zh": [
            "Giongo 标签页（手绘拟声字）这次增加了很多，但它更"
            "像是“先用用看，坏了告诉我”，而不是已经打磨好的东西。粗"
            "糙之处还在，尤其是 Liquify：画笔确实按说明工作，"
            "但很钝——用力一划会把整个词抹花，而不是轻轻推一下；没有"
            "压感、没有平滑，拖动中途也没有撤销。这里的一切都能用 C"
            "trl+Z 撤销，而且在你插入之前，页面不会被动到。",
            "现在可以直接改字了。预览上方有四个工具：移动某个字、用画"
            "笔推挤它（Liquify）、抓住轮廓自身的节点，或者擦掉"
            "一部分。改过的字仍然跟着排布、路径和逐字移动走，一次撤销"
            "就收回整整一笔。",
            "你自己的字可以当作字体来用。导入时指向图片、文件夹或 Z"
            "IP——每个文件就是它名字所写的那个字（ド.png 就是"
            " ド）——它们会被描成轮廓一次，之后就像其他字一样绘制，"
            "填充、描边一应俱全。",
            "内置 65 条常见拟声词的词典，可以选而不必打字：假名、"
            "读法和含义，德语和英语都能搜，选中时也一并带上合适的样子"
            "。",
            "外观新增：效果旁边的小字（画出的 ドカーン 下面一个小小"
            "的 “BOOM”）、为 ア゛ 和 ン゛ 准备的浊点按钮、"
            "反白、只画线和线上网点两种填充、三种手感的噪点线，以及装"
            "饰——集中线、碎片、闪光、水滴。",
            "面板里的撤销与重做接上了 Ctrl+Z 和 Ctrl+Y"
            "，每一次改动都是一步；而当你正在文本框里打字时，这两个键"
            "属于文本框。",
            "保存：每个图层各自一张 PNG 打包成 ZIP（画布一致"
            "，叠回去就是原样）、由 Krita 自己写出的 PSD，"
            "以及 PNG 和 ZIP 的 1 至 4 倍尺寸。没有安"
            "装的字体文件可以手动载入，还有一个用字体本身来显示的字体"
            "列表。",
            "这个标签页快了很多。一帧带加粗和两道描边原先要 1352"
            " 毫秒，现在是 33；拖动一个字原先每步 23 毫秒，现"
            "在是 2。加粗和描边本是同一种外扩做了两遍，而一个字的形"
            "状并不取决于它放在哪里——这两件事此前每秒要从头算六十次"
            "。",
            "拉出成独立窗口后，手绘字占据左边，设置排在旁边。窗口也终"
            "于能放进屏幕了：它过去比 1080 px 还高，又无法变"
            "矮，下边缘就落在桌面之外。",
        ],
    },
    "1.21": {
        "ja": [
            "スクリプトは読み込むだけのものではなく、書くものになりました。"
            "「+ New」で空のスクリプトを始められ、行は読んでいるその場で直せます"
            "——表で F2 か右クリック、あるいはプレビュー上の欄で——し、行の挿入・"
            "削除・並べ替えもできます。スクリプトにページ区切りが無いところには"
            "手で入れられます。「Page 12」の自動認識はそのままで、これまでどおり"
            "働きます。直した行はスクリプト本文にも書き戻されるので、Analyze が"
            "黙って元に戻してしまうことはなくなりました。",
            "Batch タブの中にスクリプトそのものが入りました。全部の行がそこに"
            "並び、チェック済みで、すでに吹き出しに割り当てられています——入れる"
            "行を指定するのではなく、入れない行のチェックを外す形です。行に"
            "直接入力でき、Enter で次の行が作られます。ページの始まりは帯で"
            "示され、タブを離れずに開いている別のスクリプトへ切り替えられます。",
            "文字が吹き出しの実際の輪郭に合うようになりました。これまでの"
            "「Round」は選択範囲を囲む矩形に楕円を内接させるもので、楕円でない"
            "形——雲、叫び、しっぽ付きの吹き出し——でははみ出していました。"
            "選択マスクこそが形なので、各行はそれが横切るいちばん狭いところで"
            "制限され、実際にある位置で中央に置かれます。矩形選択には従うべき"
            "形が無いため、これまでどおりの動作のままです。",
            "Krita のどこででも Ctrl+Space でフォント検索が開きます。数文字"
            "打てばその書体が文字に適用され、お気に入りが先頭に、各行はその"
            "書体自身で描かれます。このプレビューはオフにできます。",
            "設定にすべてのショートカットが並びます。TypeR 自身のものと、"
            "あなたが割り当てたプリセットキーが、キャラクター名・プリセット名・"
            "作品名つきで。TypeR 自身のキーはそこで割り当て直せます。すでに"
            "プリセットが持っている組み合わせは、黙って奪わずに拒否します。",
            "設定にクレジット欄ができました。機能ごとに、誰の発想で、誰が"
            "書いたかを示します。このプラグインの少なからぬ部分は他の人の発想を"
            "作り直したものであり、それをそう書くようにしました。",
            "フォントのプロパティ画面が、同じフォントの別バージョンを"
            "見つけます。Windows は「Anime Ace」「Anime Ace 2.0 BB」"
            "「Anime Ace 3 BB」を無関係な三つのファミリーとして並べますが、"
            "いまは専用の見出しの下にまとめて表示され、その上に開いている"
            "ファミリーのウェイトが並びます。",
        ],
        "zh": [
            "脚本现在是可以写的东西，而不只是载入的东西。「+ New」新建一个空"
            "脚本；一行可以在看到它的地方直接改——在表格里按 F2 或右键，或者在"
            "预览上方的输入框里——还可以插入、删除和移动行。脚本里缺少分页的"
            "地方可以手动加一个；「Page 12」的自动识别原样保留，照常工作。改过"
            "的行现在也会写回脚本正文，Analyze 不会再悄悄把它还原。",
            "Batch 标签里放的就是脚本本身。每一行都在，默认勾选并且已经和气泡"
            "配好——你要做的是取消勾选不该放的行，而不是逐个填上该放的行。可以"
            "直接在行里输入，按 Enter 新建下一行；分页用横条标出；一个下拉框"
            "可以在打开的多个脚本之间切换，不必离开这个标签。",
            "文字现在贴合气泡的真实轮廓。以前的「Round」是在选区的外接矩形里"
            "内切一个椭圆，遇到不是椭圆的形状——云朵、尖叫框、带尾巴的气泡——"
            "就会溢出。选区蒙版本身就是形状：每一行受它穿过的最窄处限制，并在"
            "它实际所在的位置居中。矩形选框没有形状可循，保持原来的行为。",
            "在 Krita 的任何地方按 Ctrl+Space 打开字体搜索：敲几个字母，字体"
            "就应用到文字上，收藏的排在最前，每一行用它自己的字体绘制。这个"
            "预览可以关掉。",
            "设置里列出了全部快捷键：TypeR 自己的，以及你自己绑定的预设键，"
            "并标明所属角色、预设和作品。TypeR 自己的键可以在那里重新绑定。"
            "已经被某个预设占用的组合会被拒绝，而不是悄悄抢过来。",
            "设置里多了致谢一栏：每个功能是谁的主意、由谁写的。这个插件有"
            "相当一部分是把别人的好主意重做了一遍，现在把这件事写明白。",
            "字体属性窗口会找出同一字体的其他版本。Windows 把「Anime Ace」"
            "「Anime Ace 2.0 BB」「Anime Ace 3 BB」列成互不相干的三个字族；"
            "现在它们归在一个标题下一起显示，上面是当前这一个的各个字重。",
        ],
    },
    "1.20": {
        "ja": [
            "Fonts タブのフォントに、プロパティ画面が付きました。お気に入りの"
            "フォントを右クリックして Properties を選ぶか、Alt+Enter を押して"
            "ください。General はそのフォントが何か、ファイルがどこにあり、"
            "どれくらいの大きさかを示します。Family は同じファミリーで"
            "インストールされている書体をすべて並べ、ダブルクリックすると"
            "その書体に切り替わります。Presets はそのフォントを使っている"
            "プリセットを、作品名・キャラクター名・プリセット名とともに"
            "一覧し、そのフォントが設定されているテキスト種別も挙げます。",
            "マウスホイールでスクロールしているときに、通りかかった"
            "スライダーやドロップダウンの値が変わってしまうことは"
            "なくなりました。ホイールは本来どおりタブをスクロールします。"
            "クリックして選んだ状態であれば、これまでどおりホイールで"
            "操作できます。",
        ],
        "zh": [
            "Fonts 标签里的字体现在有了属性窗口：右键点击收藏的字体并选择 "
            "Properties，或者按 Alt+Enter。General 说明这个字体是什么、"
            "文件在哪里、有多大；Family 列出该字族已安装的全部字重，"
            "双击其中一项即可切换过去查看；Presets 列出所有用到这个字体的"
            "预设，并标明所属作品、角色和预设名称，还会指出哪些文本类型"
            "被设成了它。",
            "滚动页面时，鼠标滚轮不会再把路过的滑块或下拉框的值改掉："
            "它只滚动标签页，本该如此。点选某个控件之后，滚轮依然可以"
            "用来调整它。",
        ],
    },
    "1.19": {
        "ja": [
            "模様（パターン）の取り込みがずっと楽になりました。繰り返し模様の"
            "一部を——スクリーンショットでもスキャンでも、量は問いません——"
            "パターン画像として読み込むだけで、TypeR が縦横それぞれ何ピクセル"
            "ごとに繰り返しているかを割り出し、タイルを並べて見せたうえで、"
            "その 1 枚に切り詰めるかどうかを尋ねます。切り抜きには模様が"
            "最低 2 回分入っている必要があります。すでに 1 タイルだけの画像は"
            "そのまま使われます。色と透明度は保たれます。",
        ],
        "zh": [
            "获取图案（pattern）省事多了：把重复图案的任意一块——截图也好、"
            "扫描也好，多少都行——当作图案图片载入，TypeR 会算出它在横向和"
            "纵向各隔多少像素重复一次，把单元块平铺出来给你看，并询问是否"
            "把这张图裁成那一块。截取的范围里至少要出现两次完整图案；"
            "本身就只有一块的图片会原样使用。颜色和透明度都会保留。",
        ],
    },
    "1.18": {
        "ja": [
            "行全体に色を付けるのに、もう選択は要りません。何も選択していない"
            "ときは、Colour ボタンがカーソルのある行をそのまま対象にします。"
            "複数行ある欄ではその 1 行だけが対象で、先に Ctrl+A を押せば"
            "すべての行に付きます。行の色は、その中の個々の単語に付けた色を"
            "置き換えます。行に対して「色を外す」を使うと、その行の色は"
            "すべて消えます。",
        ],
        "zh": [
            "给整行上色不再需要先选中文字：没有选中任何内容时，Colour "
            "按钮会直接取光标所在的那一行。输入框里有多行时只取这一行，"
            "先按 Ctrl+A 则一次给所有行上色。行的颜色会覆盖行内单个词"
            "已有的颜色；对整行使用「去掉颜色」，会把这一行里的颜色全部清除。",
        ],
    },
    "1.17": {
        "ja": [
            "単語ごとに色を付けられるようになりました。入力欄で単語を選んで "
            "Colour を押すと、その単語だけが別の色になります。ボタンは"
            "表示中の色をそのまま適用し、矢印から色の一覧・カラーピッカー・"
            "「色を外す」を開けます。色は **bold** と同じように "
            "{#e03030|word} という形で行そのものに書き込まれるので、保存や"
            "編集をしても残り、手で入力することもできます"
            "（{red|word} も有効）。縁取りと影はもとの色のままです ——"
            "それが色付きの単語を読めるようにしています。",
        ],
        "zh": [
            "可以给单个词单独上色了：在输入框里选中一个词，按 Colour，"
            "就只有那个词换成另一种颜色。按钮直接应用当前显示的颜色，"
            "旁边的箭头可以打开颜色列表、取色器和「去掉颜色」。颜色像 "
            "**bold** 一样以 {#e03030|word} 的形式写进那一行，因此保存和"
            "再次编辑都不会丢失，也可以手动输入（{red|word} 同样有效）。"
            "描边和阴影仍保持原来的颜色 —— 正是这一点让上了色的词依然看得清。",
        ],
    },
    "1.16": {
        "ja": [
            "Swap タブを追加しました。クリーンが上がったら、raw の上で"
            "仕上げた写植をそのままクリーンへ移せます。2 つのフォルダーを"
            "指定し、表を確認して（ページはファイル名の番号で対応づけられ、"
            "各行には書き込む前に何が起きるかが出ます）、転送するだけです。"
            "置き換わるのは各 .kra のいちばん下のレイヤーだけで、テキスト・"
            "ベクター・マスク・効果はバイト単位でそのまま引き継がれます。"
            "クリーンが小さい場合は拡大を許可しない限り拒否され、ページ"
            "ごとの PNG 出力は任意です（Krita がレンダリングします）。",
        ],
        "zh": [
            "新增 Swap 标签页：清图做好之后，可以把已经在 raw 上做完的嵌字"
            "整体移到清图上。指定两个文件夹，核对表格（按文件名中的页码自动"
            "配对，每一行在写入之前就会说明将要发生什么），然后点击转移即可。"
            "被替换的只有每个 .kra 最下面的那一层，文字、矢量、蒙版和效果都"
            "按字节原样保留。清图尺寸偏小时，除非你允许缩放，否则会被拒绝；"
            "每页的 PNG 输出是可选的（由 Krita 渲染）。",
        ],
    },
    "1.15": {
        "ja": [
            "新しい TypeR が公開されるとドッキングパネルが知らせます。"
            "右下のビルド表示の隣に小さな行が出て、プロジェクトページへの"
            "リンクになります。確認はバックグラウンドで、1 日に 1 回まで。"
            "送信されるのはリクエストだけで、確認が失敗しても何も言いません。"
            "問い合わせてほしくなければ Setup タブで無効にできます。",
        ],
        "zh": [
            "有新版 TypeR 发布时，工具面板会提示：右下角构建信息旁会出现一行小字，"
            "链接到项目页面。检查在后台进行，每天最多一次；除请求本身外不发送"
            "任何内容，检查失败时也保持安静。如果不希望它联网查询，"
            "可在 Setup 标签页关闭。",
        ],
    },
    "1.14": {
        "ja": [
            "Fonts タブで自分の文章をプレビューできます。新しい "
            "「Preview:」 欄に一行入力すると、一覧のすべてのフォントが"
            "その文章で描かれるので、フォント名が格好よく見えるかではなく、"
            "その台詞に合うかどうかで選べます。空欄なら従来どおりフォント名が"
            "表示され、サンプルを入れてもフォント名は背後に灰色で読めるまま"
            "残ります。",
        ],
        "zh": [
            "Fonts 标签页可以预览你自己的文字：在新的 「Preview:」 "
            "输入框里写一行，列表中每种字体都会用这行字来显示，于是你看到的是"
            "哪种字体适合这句台词，而不是哪种字体把自己的名字写得好看。"
            "留空则和以往一样显示字体名；填了示例文字，字体名仍以灰色显示在"
            "后面，依然读得出来。",
        ],
    },
    "1.13": {
        "ja": [
            "台本を PDF から直接読み込めます。日本語／英語の 2 列の表は"
            "そのまま対として読み込まれ、「Page 3」 のような行は"
            "従来どおりページ区切りとして扱われます。表のセル内で折り返された"
            "文は 1 行につなぎ直されます。スキャン画像のページには読み取れる"
            "文字がないため、その旨を表示します — 先に OCR が必要です。",
        ],
        "zh": [
            "可以直接从 PDF 读取脚本。日文／英文的双列表格会自动成对读入，"
            "「Page 3」 这类行仍按页码标记处理。在表格单元格内换行的"
            "文字会重新合并成一行。扫描图片的页面没有可读取的文字，程序会"
            "明确说明 — 这类页面需要先做 OCR。",
        ],
    },
    "1.12": {
        "ja": [
            "プリセットのキー割り当て：スタイルにキーを割り当てておけば、"
            "話者が変わったときにキーを押すだけで切り替わります。キャラクターと"
            "プリセットのドロップダウンをたどる必要はありません。入力欄は"
            "プリセット一覧の下にあります。",
            "キー割り当ては Ctrl+C と同じように複数キーの組み合わせにできます。"
            "通常の文字キーも組み合わせに数えるので、A+B は「A を押したまま "
            "B を押す」という意味です。順序も区別されるため、B+A は別の"
            "割り当てです。",
            "A に Akarie、A+B に Akarie Bold を同時に割り当てられます。"
            "A を押した時点で Akarie が適用され、そのまま B を足すと "
            "Bold に切り替わります。",
            "キー割り当ては作品ごとに保存されるので、次のシリーズでは"
            "同じ数個のキーをまた使えます。",
            "Google ドキュメントの台本が再び読み込めます。Drive が"
            "どのプログラムにも .gdoc の中身を読ませなくなったため、TypeR は "
            "Drive クライアント自身のインデックスから文書を探し、"
            "見つからなければリンクの入力を求めます。",
        ],
        "zh": [
            "预设快捷键：给一种样式指定一个按键，换人说话时直接按键即可，"
            "不用再逐个点开角色和预设下拉框。输入框就在预设列表下方。",
            "快捷键可以像 Ctrl+C 那样组合多个按键，而且普通字母也算在内："
            "A+B 表示按住 A 再按 B。顺序同样有区别，所以 B+A 是另一个快捷键。",
            "可以同时把 A 绑定到 Akarie、把 A+B 绑定到 Akarie Bold："
            "按下 A 就立刻应用 Akarie，再加按 B 便切换到粗体那一个。",
            "快捷键按作品分别保存，所以换到下一部作品时，"
            "同样这几个按键又空出来了。",
            "Google 文档脚本又能读取了。由于 Drive 已不再允许任何程序读取 "
            ".gdoc 文件本身，TypeR 改为在 Drive 客户端自己的索引中查找该文档；"
            "若查不到，就请你提供链接。",
        ],
    },
    "1.11": {
        "ja": [
            "Batch タブ：ページの吹き出しを登録し、それぞれに台詞を対応させて"
            "一度にまとめて流し込めます。各吹き出しには TextShapR が推奨する"
            "形で収めます。吹き出しごとに止まって確認できるレビューモード、"
            "行単位でのフォントとプリセットの上書き、そして流し込みが作った"
            "ものだけを正確に取り消す Undo batch が付きます。",
            "Krita 6 で動作します。Qt バインディングは起動時に選ばれ"
            "（Krita 6.0 以降は PyQt6、5.x は PyQt5）、同じインストールの"
            "ままどちらでも使えます。どちらが検出されたかは Setup タブに"
            "表示されます。",
            "フォントは Windows のレジストリではなくフォントファイル自体を"
            "読んで探します。再パッケージされたファミリーや、ファミリーの "
            "Bold・Italic のウェイトもようやく見つかります。綴りが少し違う"
            "名前でも目的のフォントに届きます。",
            "TextShapR は行数を固定値ではなく吹き出しの形から決め、"
            "候補を読みやすさの順に並べます。",
            "主要キャラクター：毎ページ話す数人を登録しておくと、"
            "キャラクターとプリセットのドロップダウンの先頭に並びます。",
            "フォント同梱の書き出し：お気に入りとプリセットを JSON と一緒に"
            "実際のフォントファイルごと書き出し、別のマシンでそのまま"
            "入れられます。プリセットは Excel の表としても書き出せます。",
        ],
        "zh": [
            "Batch 标签页：先标出一页里的气泡，把每个气泡与对应的台词配好，"
            "然后一次性全部排入，每个都按 TextShapR 推荐的形状来适配。"
            "附带逐个气泡停下确认的审阅模式、可按行单独覆盖字体与预设，"
            "以及只撤销本次排版所创建内容的 Undo batch。",
            "支持 Krita 6：Qt 绑定在启动时自动选择（Krita 6.0 及以上用 "
            "PyQt6，5.x 用 PyQt5），同一份安装在两者上都能用。"
            "检测到的是哪一个，会显示在 Setup 标签页。",
            "查找字体时直接读取字体文件本身，而不是 Windows 注册表，"
            "所以被重新打包的字体家族、以及家族里的 Bold 和 Italic 字重"
            "终于都能找到了；名字拼写稍有差别，也仍然能对上相应的字体。",
            "TextShapR 的行数不再是固定值，而是根据气泡的形状决定，"
            "并按易读程度为候选排序。",
            "主要角色：把每页都说话的那几位标为主要角色，"
            "他们就会排在角色和预设下拉框的最前面。",
            "字体打包：导出收藏和预设时，会连同实际的字体文件一起随 JSON "
            "导出，并可在另一台机器上直接安装。预设还可以导出为 Excel 表格。",
        ],
    },
    "1.9": {
        "ja": [
            "自分で描いた選択範囲をパターンやグラデーションで塗れます。",
            "網点（スクリーントーン）のグラデーション（密から疎へ）を"
            "方向付きで、さらに斜線・砂目・きらめきの網点を追加しました。",
            "TextShapR：選んだ形はそのまま保たれます。サイズ・フォント・色・"
            "縁取りを変えても、形が勝手に組み直されることはなくなりました。",
            "Fonts タブ：プレビューの大きさを変えられるようになり、"
            "一覧の表示もかなり速くなりました。",
        ],
        "zh": [
            "可以用图案或渐变填充你自己绘制的选区。",
            "网点（screentone）渐变（由密到疏）可指定方向，"
            "另外新增斜线、沙目和闪光网点。",
            "TextShapR：你选定的形状会保持不变 — 修改字号、字体、颜色"
            "或描边，不会再悄悄把它重新排成别的形状。",
            "Fonts 标签页：预览尺寸可调，列表也快了很多。",
        ],
    },
    "1.8": {
        "ja": [
            "Style タブ：パターンで塗った縁取りとぼかした縁取り、"
            "そして文字そのもののパターン塗りを追加しました。",
            "パターン生成とパターンライブラリ：作って名前を付けて保存し、"
            "後からサムネイルで選べます。",
            "Setup に 「Missing fonts」 ウィンドウを追加しました。"
            "台本が要求しているのに、この環境に入っていないフォントを"
            "一覧表示します。",
            "Fonts タブ：フォントピッカーから直接、ワンクリックで"
            "お気に入り登録、右クリックで分類ができます。",
            "主要タブの並び順が崩れる不具合を修正しました。すでに誤った順序で"
            "保存されていた場合も、一度だけ自動で直します。",
        ],
        "zh": [
            "Style 标签页：新增用图案填充的描边和柔化（模糊）描边，"
            "以及文字本身的图案填充。",
            "图案生成器和图案库：做好一个图案，命名保存，"
            "之后从缩略图里直接选用。",
            "Setup 中新增 「Missing fonts」 窗口，"
            "列出脚本要求、但本机没有安装的字体。",
            "Fonts 标签页：在字体选择器里即可一键收藏，右键分类。",
            "修复了主标签页顺序错乱的问题，"
            "并对已经被错误保存的顺序做一次性修正。",
        ],
    },
}

#: version -> fingerprint of the English the translation above was made from.
#: Written by `--stamp`; never edited by hand.
EN_FINGERPRINT = {
    "1.8": "34374ac722fe",
    "1.9": "5c7885a476ed",
    "1.11": "f6d99a22f7ae",
    "1.12": "5b8d8245819b",
    "1.13": "fd8b5b30d79d",
    "1.14": "afb743ae6582",
    "1.15": "00e32ac49fab",
    "1.16": "8b7b7736f275",
    "1.17": "218fe6a77a8f",
    "1.18": "7482447ffb1c",
    "1.19": "3edbc0e7e945",
    "1.20": "41d844327a84",
    "1.21": "4e46a8a1d9e0",
    "1.22": "ef3a616d51a5",
}


def fingerprint(lines):
    """A short, stable hash of one version's English lines."""
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:12]


def english(path=WHATSNEW):
    """{version: [english line, ...]} from the plugin's changelog."""
    spec = importlib.util.spec_from_file_location("typer_whatsnew_src", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict((ver, langs.get("en", [])) for ver, langs in mod.CHANGELOG)


def problem_with(version, en_lines):
    """Why `version` cannot be released yet, or None.

    Separate from the release script so the state of the translations can be
    checked at any time, not only when something is being published.
    """
    entry = NOTES.get(version)
    if not entry:
        return ("no translation for %s in tools/release_i18n.py" % version)
    for lang, _heading in SECTIONS:
        if lang == "en":
            continue
        lines = entry.get(lang)
        if not lines:
            return "the %s translation for %s is missing" % (lang, version)
        if len(lines) != len(en_lines):
            return ("the %s translation for %s has %d line(s), the English has "
                    "%d - they are read side by side"
                    % (lang, version, len(lines), len(en_lines)))
    want = fingerprint(en_lines)
    have = EN_FINGERPRINT.get(version)
    if have is None:
        return ("%s has no fingerprint - run tools/release_i18n.py --stamp "
                "once the translation matches the English" % version)
    if have != want:
        return ("the English for %s changed since it was translated (%s -> %s)"
                " - re-read the translation, then --stamp" % (version, have, want))
    return None


def stamp():
    """Rewrite EN_FINGERPRINT from the current English. Checked in."""
    eng = english()
    out = {}
    for version in sorted(NOTES, key=lambda v: [int(p) for p in v.split(".")]):
        if version not in eng:
            print("  !! %s is translated but has no changelog entry" % version)
            continue
        out[version] = fingerprint(eng[version])
    body = "".join('    "%s": "%s",\n' % (v, out[v])
                   for v in sorted(out, key=lambda v: [int(p) for p in v.split(".")]))
    text = io.open(SELF, encoding="utf-8").read()
    new = re.sub(r"EN_FINGERPRINT = \{\n(?:.*?\n)??\}",
                 "EN_FINGERPRINT = {\n" + body + "}", text, count=1, flags=re.S)
    if new == text:
        raise SystemExit("could not find the EN_FINGERPRINT block to rewrite")
    io.open(SELF, "w", encoding="utf-8", newline="\n").write(new)
    print("stamped %d version(s)" % len(out))
    return 0


def check():
    """Report on every version in the changelog. Non-zero if any is unusable."""
    eng = english()
    bad = 0
    for version in sorted(eng, key=lambda v: [int(p) for p in v.split(".")]):
        why = problem_with(version, eng[version])
        if why:
            bad += 1
            print("  FAIL %-6s %s" % (version, why))
        else:
            print("  ok   %-6s %d line(s) in %d languages"
                  % (version, len(eng[version]), len(SECTIONS)))
    extra = set(NOTES) - set(eng)
    for version in sorted(extra):
        print("  ??   %-6s translated but not in the changelog" % version)
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stamp", action="store_true",
                    help="record the English each translation was made from")
    ap.add_argument("--check", action="store_true",
                    help="is every changelog version translated and current?")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):            # pragma: no cover
        pass
    if args.stamp:
        return stamp()
    return check()


if __name__ == "__main__":
    sys.exit(main())
