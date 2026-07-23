/* ============================================================
   家庭AI智能体选型推荐 — 数据 & 交互逻辑
   支持：编辑模式、模态编辑、导入导出、雷达图
   ============================================================ */

// ==================== 默认数据定义 ====================
const DEFAULT_DATA = {
    categories: [
        {
            id: 'domestic',
            name: '国内消费级闭环生态Agent',
            icon: '🇨🇳',
            desc: '以小米、华为、美的为代表的国内品牌，依托自有IoT生态实现深度家电控制，适合品牌忠诚度高的家庭用户。特点：生态闭环体验好，跨品牌兼容性弱，性价比高。',
            colorClass: 'cat-domestic',
            products: ['xiaomi_miloco', 'huawei_xiaoyi', 'midea_mevox']
        },
        {
            id: 'cross',
            name: '跨品牌通用中枢Agent',
            icon: '🔗',
            desc: '涂鸦、Home Assistant、移动灵犀等平台型产品，以多协议兼容和跨品牌联动为核心竞争力，适合多品牌混搭家庭和租房场景。特点：设备兼容性极强，灵活可扩展。',
            colorClass: 'cat-cross',
            products: ['tuya_hey', 'home_assistant', 'yidong_lingxi']
        },
        {
            id: 'overseas',
            name: '海外生态Agent',
            icon: '🌍',
            desc: 'Alexa+、Gemini Home、Apple Intelligence等海外科技巨头产品，依托全球化AI能力和多语言支持，适合海外华人和英语环境家庭。特点：AI能力强，国内本土化弱。',
            colorClass: 'cat-overseas',
            products: ['alexa_plus', 'gemini_home', 'apple_intelligence']
        },
        {
            id: 'villa',
            name: '高端本地别墅智能体',
            icon: '🏰',
            desc: '面向大户型别墅的高端定制方案，强调本地化部署、隐私安全、全宅智能集成。通常需要专业团队安装部署，成本高但体验极致。',
            colorClass: 'cat-villa',
            products: ['ha_enterprise', 'crestron_home', 'custom_local']
        }
    ],

    products: {
        xiaomi_miloco: {
            name: '小米 Miloco 2.0',
            category: 'domestic',
            model: 'MiLM-7B (端侧) + 云端 MiLM-13B',
            multiAgent: '4个子Agent协作(家电/安防/健康/娱乐)，通过Xiaomi HyperMind调度',
            memory: '长期家庭记忆图谱(LTM Graph)，支持72小时上下文窗口，主动学习用户习惯',
            protocol: 'MiHome私有协议 + 部分Matter支持，覆盖2000+ SKU',
            privacy: '端侧推理主模型，敏感数据本地处理，云端可选加密同步',
            cost: '中枢硬件 ¥299-599，无需月费',
            barrier: '极低，APP一键配网，语音+触控双模交互',
            scene: '小米生态全家桶用户、智能家居入门、中小户型公寓',
            score: 4.2,
            scores_detail: { model: 4.0, multiAgent: 4.0, memory: 4.5, protocol: 3.5, privacy: 4.5, cost: 4.5, barrier: 5.0, scene: 4.0 }
        },
        huawei_xiaoyi: {
            name: '华为鸿蒙小艺',
            category: 'domestic',
            model: '盘古大模型3.0 (端云协同) + 鸿蒙原生AI引擎',
            multiAgent: '6个子Agent(全屋/出行/办公/健康/娱乐/教育)，分布式软总线协同',
            memory: '鸿蒙原子化服务记忆，跨设备无缝流转，场景自动识别',
            protocol: 'HarmonyOS Connect (HiLink升级)，支持Matter/Thread，覆盖1500+品类',
            privacy: '端侧TEE安全隔离，数据分类分级加密，HarmonyOS隐私中心透明管理',
            cost: '华为智能音箱 ¥399-899 / 智慧屏 ¥2499+',
            barrier: '低，鸿蒙手机用户无缝上手，非鸿蒙用户需下载智慧生活APP',
            scene: '华为全家桶用户、鸿蒙生态家庭、全屋智能新房装修',
            score: 4.3,
            scores_detail: { model: 4.5, multiAgent: 4.5, memory: 4.5, protocol: 4.0, privacy: 5.0, cost: 3.5, barrier: 4.0, scene: 4.5 }
        },
        midea_mevox: {
            name: '美的 MevoX',
            category: 'domestic',
            model: '美的大模型 (家电垂直领域微调) + 多模态感知',
            multiAgent: '3个核心Agent(厨房/空气/洗护)，基于家电知识图谱协同',
            memory: '家庭饮食+能耗记忆，智能补货提醒，季节性场景推荐',
            protocol: 'M-Smart协议 + 美的私有云，支持天猫精灵/小度对接，覆盖3000+ SKU',
            privacy: '家电数据本地优先，云端用于AI优化，符合等保三级',
            cost: '美的智能家电自带AI功能，额外中枢 ¥199-399',
            barrier: '极低，使用美的家电自动接入，无需额外学习',
            scene: '美的家电用户、厨房场景深度优化、全屋家电以旧换新',
            score: 3.8,
            scores_detail: { model: 3.5, multiAgent: 3.5, memory: 4.0, protocol: 3.5, privacy: 4.0, cost: 4.5, barrier: 4.5, scene: 3.5 }
        },
        tuya_hey: {
            name: '涂鸦 Hey Tuya',
            category: 'cross',
            model: '涂鸦AI中台 (GPT-4o mini + 自研小模型)',
            multiAgent: '开放Agent框架，支持第三方Agent接入，IoT PaaS级协同',
            memory: '云端场景模板记忆，用户自定义自动化规则持久化',
            protocol: 'Tuya IoT PaaS协议栈，支持WiFi/BLE/Zigbee/Matter/Thread全协议，全球2800+品牌兼容',
            privacy: '云端为主，可选区域化部署(SG/FRA/DE节点)，GDPR合规',
            cost: '涂鸦网关 ¥99-299，PaaS平台按设备量计费(个人免费额度)',
            barrier: '低~中，配网简单但高级自动化需要一定配置能力',
            scene: '多品牌混搭家庭、跨境电商卖家、小型公寓智能化改造',
            score: 4.0,
            scores_detail: { model: 4.0, multiAgent: 4.5, memory: 3.5, protocol: 5.0, privacy: 3.5, cost: 4.5, barrier: 3.5, scene: 4.0 }
        },
        home_assistant: {
            name: 'Home Assistant',
            category: 'cross',
            model: '可接入GPT-4o/Claude/Llama等任意LLM (通过Conversation Agent集成)',
            multiAgent: '社区驱动，2000+集成插件，YAML自动化引擎 + Blueprint模板',
            memory: '本地SQLite存储，完全可控的长期数据留存，无厂商锁定',
            protocol: '开源协议适配之王，支持Zigbee2MQTT/ZWave/Matter/HomeKit/ESPhome等所有主流协议',
            privacy: '完全本地部署，数据100%私有化，零云端依赖(可选项)',
            cost: '硬件 ¥200-800 (树莓派/MiniPC)，软件免费开源，时间成本高',
            barrier: '高，需要Linux/YAML基础，社区文档丰富但学习曲线陡峭',
            scene: '技术发烧友、全屋DIY智能、隐私敏感用户、多品牌终极整合',
            score: 4.4,
            scores_detail: { model: 5.0, multiAgent: 5.0, memory: 4.5, protocol: 5.0, privacy: 5.0, cost: 4.0, barrier: 2.0, scene: 5.0 }
        },
        yidong_lingxi: {
            name: '移动灵犀',
            category: 'cross',
            model: '中国移动九天大模型 + 智能家居垂直模型',
            multiAgent: '3个Agent(家庭/社区/康养)，结合运营商网络能力',
            memory: '云端家庭数字档案，结合移动号码的跨场景记忆',
            protocol: '中国移动Andlink协议 + 家宽融合，支持主流品牌对接',
            privacy: '运营商级数据安全，等保三级认证，数据不出省',
            cost: '移动宽带融合套餐 ¥58/月起，赠送智能音箱/网关',
            barrier: '低，运营商上门安装，电话客服支持',
            scene: '移动宽带用户、中老年家庭、社区养老场景、三四线城市',
            score: 3.5,
            scores_detail: { model: 3.5, multiAgent: 3.0, memory: 3.5, protocol: 3.5, privacy: 4.0, cost: 4.5, barrier: 4.5, scene: 3.0 }
        },
        alexa_plus: {
            name: 'Alexa+',
            category: 'overseas',
            model: 'Amazon Nova + Claude 3.5 Sonnet (新一代Alexa LLM)',
            multiAgent: 'Skill生态下的多Agent，API集成第三方服务，Routines自动化',
            memory: '用户偏好云端记忆，购物历史+媒体消费习惯学习',
            protocol: 'Zigbee/BLE Mesh/WiFi/Matter/Thread，Sidewalk社区网络，兼容10万+设备',
            privacy: '云端为主，可选Do Not Send Voice Recording，AWS加密存储',
            cost: 'Echo设备 $49.99-$249.99，无月费(订阅Alexa+ $19.99/月可选)',
            barrier: '低，语音优先交互，英文为主，中文支持有限',
            scene: '英语环境家庭、Amazon生态用户、海外华人、租房公寓',
            score: 4.1,
            scores_detail: { model: 4.5, multiAgent: 4.0, memory: 4.0, protocol: 4.5, privacy: 3.5, cost: 4.0, barrier: 4.5, scene: 4.0 }
        },
        gemini_home: {
            name: 'Gemini Home',
            category: 'overseas',
            model: 'Gemini 2.0 Ultra (多模态家庭场景定制)',
            multiAgent: 'Google Home生态Agent，Nest设备深度协同，Google Assistant升级版',
            memory: 'Google Knowledge Graph家庭版，跨Google服务记忆(Calendar/Maps/Photos)',
            protocol: 'Matter/Thread核心支持 + Nest Weave，兼容主流品牌但不覆盖中国品牌',
            privacy: 'Google隐私控制台统一管理，可选本地Nest Hub处理敏感数据',
            cost: 'Nest Hub ¥599-1299，Nest音箱 ¥399-699',
            barrier: '低~中，Google生态用户无缝，但中国大陆服务受限需特殊网络',
            scene: '海外Google生态用户、英语/多语言家庭、智能安防深度需求',
            score: 4.0,
            scores_detail: { model: 5.0, multiAgent: 4.0, memory: 4.5, protocol: 3.5, privacy: 3.5, cost: 4.0, barrier: 3.5, scene: 4.0 }
        },
        apple_intelligence: {
            name: 'Apple Intelligence',
            category: 'overseas',
            model: 'Apple On-Device LLM (3B) + Private Cloud Compute (PCC) + 第三方GPT接入',
            multiAgent: 'Siri + App Intents + Shortcuts，端侧Agent调度，严控权限',
            memory: '端侧语义索引(App Intents)，Personal Context理解，跨Apple设备记忆',
            protocol: 'HomeKit (HAP) + Matter，设备兼容最少但最安全，精致生态',
            privacy: '行业标杆，端侧优先+PCC加密验证，Apple隐私承诺',
            cost: 'HomePod ¥2299 / Apple TV ¥1299，需要iPhone/iPad作为中枢',
            barrier: '低，Apple用户零学习成本，非Apple用户不可用',
            scene: 'Apple全家桶用户、隐私极致追求者、海外英语环境',
            score: 4.0,
            scores_detail: { model: 4.5, multiAgent: 3.5, memory: 4.0, protocol: 3.0, privacy: 5.0, cost: 3.0, barrier: 4.0, scene: 3.5 }
        },
        ha_enterprise: {
            name: 'Home Assistant Enterprise',
            category: 'villa',
            model: '自定义接入Claude 3.5 Opus / GPT-4o + 本地Llama 3.1 70B',
            multiAgent: '全定制Agent集群(安防/能源/灌溉/影音/照明/新风)，MQTT事件总线',
            memory: 'PostgreSQL/TimescaleDB长期存储，家庭数字孪生(Digital Twin)',
            protocol: 'KNX/DALI/Modbus/Crestron/Lutron专业总线 + Zigbee/WiFi，全协议覆盖',
            privacy: '完全本地化部署，VPN远程访问，军工级安全隔离',
            cost: '服务器 ¥3000-8000 + 专业部署 ¥5000-20000，年维护 ¥2000-5000',
            barrier: '极高，需要专业集成商部署维护',
            scene: '独栋别墅、大平层豪宅、私人影院、酒窖温控、全宅AI管家',
            score: 4.6,
            scores_detail: { model: 5.0, multiAgent: 5.0, memory: 5.0, protocol: 5.0, privacy: 5.0, cost: 2.0, barrier: 1.5, scene: 5.0 }
        },
        crestron_home: {
            name: 'Crestron Home',
            category: 'villa',
            model: 'Crestron AI引擎 + 第三方LLM可选接入',
            multiAgent: '专业级Agent(影音/灯光/窗帘/温控/安防)，Crestron Pyng调度',
            memory: 'Crestron Fusion云管理平台，商业级日志和场景记录',
            protocol: 'Crestron自有协议为主，支持Cresnet/InfiniNET，可桥接KNX/DALI/BACnet',
            privacy: '本地处理器为主，Crestron XiO云可选，商业级安全',
            cost: '主机 ¥8000-30000 + 编程部署 ¥15000-50000，年授权费 ¥3000',
            barrier: '极高，必须由Crestron认证工程师编程',
            scene: '超高端别墅、商业空间、影音发烧友、定制化程度极高',
            score: 4.3,
            scores_detail: { model: 4.0, multiAgent: 4.5, memory: 4.5, protocol: 4.5, privacy: 4.5, cost: 1.5, barrier: 1.0, scene: 4.5 }
        },
        custom_local: {
            name: '定制本地方案',
            category: 'villa',
            model: '完全定制，可选Llama 3.1 405B/Qwen2 72B/DeepSeek R1等顶级开源模型',
            multiAgent: '完全定制化Agent架构，CrewAI/AutoGen/自研框架',
            memory: '自建向量数据库(Milvus/Qdrant) + Neo4j知识图谱，无限记忆',
            protocol: '全协议定制对接，可桥接任意协议，专业弱电集成',
            privacy: '100%本地化，气隙隔离(可选)，等保三级/涉密级定制',
            cost: 'GPU服务器 ¥15000-80000 + 部署 ¥20000-100000+，年维护 ¥5000-15000',
            barrier: '极高，需要AI工程师+弱电工程师联合交付',
            scene: '科技极客豪宅、隐私至上用户、企业级家庭部署',
            score: 4.8,
            scores_detail: { model: 5.0, multiAgent: 5.0, memory: 5.0, protocol: 5.0, privacy: 5.0, cost: 1.0, barrier: 1.0, scene: 4.5 }
        }
    },

    dimensions: [
        { id: 'model', name: '底层大模型架构', icon: '🧠', desc: 'AI能力核心，决定理解与生成能力上限' },
        { id: 'multiAgent', name: '多Agent协同能力', icon: '🤝', desc: '多个AI子智能体分工协作效率' },
        { id: 'memory', name: '主动智能/长期记忆', icon: '🕰️', desc: '学习用户习惯，主动提供服务的智能程度' },
        { id: 'protocol', name: '设备兼容协议', icon: '🔌', desc: '支持的家电品牌与通信协议广度' },
        { id: 'privacy', name: '本地/云端数据隐私', icon: '🔐', desc: '数据安全等级、本地化程度、隐私保护' },
        { id: 'cost', name: '硬件成本', icon: '💰', desc: '硬件采购+部署+运维的综合成本' },
        { id: 'barrier', name: '使用门槛', icon: '🚪', desc: '上手难度、学习成本、日常维护复杂度' },
        { id: 'scene', name: '适配家庭场景', icon: '🏠', desc: '最适合的家庭类型和使用场景匹配度' }
    ],

    personas: [
        {
            id: 'newbie',
            name: '👶 新手家庭',
            desc: '刚接触智能家居，希望简单上手、快速体验AI管家便利。预算敏感，不希望复杂配置。',
            recommendations: [
                { product: 'xiaomi_miloco', type: 'best', reason: '极低使用门槛，APP一键配网，小米生态产品性价比极高，适合智能家居入门。MiLM端侧模型保障隐私，无需额外月费。', score: 4.5 },
                { product: 'tuya_hey', type: 'alt', reason: '如需兼容多品牌家电，涂鸦是低门槛跨品牌方案，个人免费额度足够家庭使用。', score: 4.0 }
            ]
        },
        {
            id: 'huawei_user',
            name: '📱 华为生态用户',
            desc: '已深度使用华为手机/平板/手表，希望智能家居无缝融入鸿蒙生态，享受分布式体验。',
            recommendations: [
                { product: 'huawei_xiaoyi', type: 'best', reason: '鸿蒙小艺与华为设备深度协同，盘古大模型+分布式软总线是核心竞争力，全屋智能体验业界领先。', score: 4.8 },
                { product: 'ha_enterprise', type: 'alt', reason: '如别墅用户需要更高自由度，可基于HA+鸿蒙桥接打造混合方案。', score: 4.3 }
            ]
        },
        {
            id: 'custom_home',
            name: '🏗️ 全屋家电定制',
            desc: '新房装修或全屋翻新，计划统一规划智能家居，预算充裕，追求极致全屋体验。',
            recommendations: [
                { product: 'huawei_xiaoyi', type: 'best', reason: '鸿蒙全屋智能方案最成熟，从布线到设备选型一站式，华为智选生态品质有保障。', score: 4.5 },
                { product: 'ha_enterprise', type: 'best', reason: '对自由度要求高可选HA企业部署，全协议支持+无限定制，适合独栋/大平层。', score: 4.6 },
                { product: 'crestron_home', type: 'alt', reason: '预算充足且追求商业级稳定可考虑Crestron，影音体验无可匹敌。', score: 4.2 }
            ]
        },
        {
            id: 'renter_mix',
            name: '🔀 多品牌混搭租房',
            desc: '租房场景，家电品牌驳杂（可能是房东配的+自己买的），需要通过一个中枢统一管理。',
            recommendations: [
                { product: 'tuya_hey', type: 'best', reason: '涂鸦兼容2800+品牌，几乎囊括市面所有智能家电。租房无需布线改造，WiFi即插即用。搬家可带走。', score: 4.5 },
                { product: 'home_assistant', type: 'best', reason: '如果愿意投入学习，HA是终极混搭方案，任何协议任何品牌都能统一管理。', score: 4.2 },
                { product: 'xiaomi_miloco', type: 'alt', reason: '如果大部分设备是小米系，Miloco性价比极高。', score: 3.8 }
            ]
        },
        {
            id: 'enthusiast',
            name: '🤖 技术发烧友',
            desc: '技术背景深厚，喜欢DIY和深度定制，追求极致可控性和前沿技术体验。',
            recommendations: [
                { product: 'home_assistant', type: 'best', reason: '开源社区驱动，2000+插件，可接入任何LLM，完全本地化部署。YAML自动化+Node-RED可视化编程，是技术玩家的终极乐园。', score: 5.0 },
                { product: 'custom_local', type: 'best', reason: '不差钱版本：自建GPU集群跑70B大模型，Neo4j知识图谱+VLM视觉理解，完全定制化Agent集群。', score: 4.5 },
                { product: 'ha_enterprise', type: 'alt', reason: '折中方案：专业集成商搞定布线硬件，自己负责软件和AI层定制。', score: 4.3 }
            ]
        },
        {
            id: 'overseas_user',
            name: '✈️ 海外用户',
            desc: '长期居住海外（北美/欧洲/东南亚），需要当地语言支持和本地化服务，或需要远程管理国内房产。',
            recommendations: [
                { product: 'alexa_plus', type: 'best', reason: '北美首选，Amazon生态覆盖全面，Echo设备性价比高，英文语音体验最佳。新一代LLM加持后AI能力大幅提升。', score: 4.3 },
                { product: 'apple_intelligence', type: 'best', reason: 'Apple用户首选，隐私保护业界标杆，HomeKit Secure Video安全可靠。', score: 4.2 },
                { product: 'gemini_home', type: 'alt', reason: 'Google生态重度用户可选，Gemini多模态能力领先，Nest安防体系成熟。', score: 4.0 },
                { product: 'home_assistant', type: 'alt', reason: '如需要同时管理海外和国内设备，HA+远程VPN方案是最灵活的跨国方案。', score: 4.0 }
            ]
        },
        {
            id: 'villa_owner',
            name: '🏰 高端别墅用户',
            desc: '独栋/联排别墅，面积300㎡+，需要专业级全宅智能化，包括影音/安防/园林/泳池/酒窖等。',
            recommendations: [
                { product: 'custom_local', type: 'best', reason: '完全定制方案，从弱电布线到AI Agent架构全部量身打造。本地4090/5090服务器跑大模型，全协议桥接，军工级隐私。', score: 4.8 },
                { product: 'ha_enterprise', type: 'best', reason: '基于HA的企业级部署，成本可控且开源透明，专业集成商交付。是目前最成熟的别墅方案。', score: 4.7 },
                { product: 'crestron_home', type: 'alt', reason: '传统豪宅标配，影音控制无可替代，但AI能力相对保守，适合重视稳定性的用户。', score: 4.3 }
            ]
        }
    ]
};

// ==================== 运行时状态 ====================
let DATA = null;           // 当前数据
let editMode = false;      // 编辑模式开关
let modalTarget = null;    // 编辑弹窗目标
let selectedDims = [];     // 维度矩阵选中的品类
let radarProducts = [];    // 雷达图选中的产品

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    initTabs();
    initDimensionCheckboxes();
    initRadarCheckboxes();
});

function loadData() {
    const saved = localStorage.getItem('home_ai_recommend_data');
    if (saved) {
        try { DATA = JSON.parse(saved); } catch (e) { DATA = null; }
    }
    if (!DATA) {
        DATA = JSON.parse(JSON.stringify(DEFAULT_DATA));
    }
    renderAll();
}

function saveData() {
    localStorage.setItem('home_ai_recommend_data', JSON.stringify(DATA));
}

function resetToDefault() {
    if (confirm('确定要恢复为默认数据吗？所有修改将丢失。')) {
        DATA = JSON.parse(JSON.stringify(DEFAULT_DATA));
        saveData();
        renderAll();
    }
}

// ==================== 标签页切换 ====================
function initTabs() {
    document.querySelectorAll('#mainTabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#mainTabs .tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const tabId = btn.dataset.tab;
            document.getElementById('panel-' + tabId).classList.add('active');
            if (tabId === 'scoring') {
                renderScoring();
            }
        });
    });
}

// ==================== 全部渲染 ====================
function renderAll() {
    renderOverview();
    renderCategories();
    renderDimensionMatrix();
    renderPersonas();
    renderScoring();
}

// ==================== 总览对比表格 ====================
function renderOverview() {
    const tbody = document.getElementById('overviewBody');
    const dims = ['model','multiAgent','memory','protocol','privacy','cost','barrier','scene'];
    let html = '';
    for (const cat of DATA.categories) {
        for (let i = 0; i < cat.products.length; i++) {
            const pid = cat.products[i];
            const p = DATA.products[pid];
            if (!p) continue;
            html += '<tr>';
            html += '<td><span class="cat-tag ' + cat.colorClass + '">' + cat.name + '</span></td>';
            html += '<td><strong>' + p.name + '</strong></td>';
            for (const dim of dims) {
                html += '<td class="editable-cell" data-edit="product.' + pid + '.' + dim + '" onclick="openCellEdit(\'' + pid + '\',\'' + dim + '\')">' + escapeHtml(p[dim] || '-') + '</td>';
            }
            html += '<td class="col-score editable-cell" data-edit="product.' + pid + '.score" onclick="openCellEdit(\'' + pid + '\',\'score\')">';
            html += renderStars(p.score);
            html += '</td>';
            html += '</tr>';
        }
    }
    tbody.innerHTML = html;
    updateEditModeUI();
}

function renderStars(score) {
    let s = '<span class="score-stars">';
    for (let i = 1; i <= 5; i++) {
        if (i <= Math.floor(score)) s += '★';
        else if (i - 0.5 <= score) s += '★';  // half star approximation
        else s += '<span class="dim">★</span>';
    }
    s += ' <small>' + score.toFixed(1) + '</small></span>';
    return s;
}

// ==================== 品类卡片 ====================
function renderCategories() {
    const grid = document.getElementById('categoryGrid');
    let html = '';
    for (const cat of DATA.categories) {
        html += '<div class="category-card ' + cat.colorClass + '" onclick="openCategoryDetail(\'' + cat.id + '\')">';
        html += '<h3><span class="cat-icon">' + cat.icon + '</span>' + cat.name + '</h3>';
        html += '<p class="cat-desc">' + cat.desc + '</p>';
        html += '<div class="cat-products">';
        for (const pid of cat.products) {
            const p = DATA.products[pid];
            html += '<span class="cat-product-tag">' + (p ? p.name : pid) + '</span>';
        }
        html += '</div>';
        html += '<div class="cat-meta">👆 点击查看该品类下所有产品详细对比</div>';
        html += '</div>';
    }
    grid.innerHTML = html;
}

function openCategoryDetail(catId) {
    const cat = DATA.categories.find(c => c.id === catId);
    if (!cat) return;
    document.getElementById('categoryModalTitle').textContent = cat.icon + ' ' + cat.name;
    const pids = cat.products;
    const dims = DATA.dimensions;
    let html = '<p style="margin-bottom:16px;color:var(--text-secondary)">' + cat.desc + '</p>';
    html += '<table class="cat-detail-table"><thead><tr><th>产品</th>';
    for (const d of dims) {
        html += '<th>' + d.icon + ' ' + d.name + '</th>';
    }
    html += '<th>⭐ 综合</th></tr></thead><tbody>';
    for (const pid of pids) {
        const p = DATA.products[pid];
        if (!p) continue;
        html += '<tr><td><strong>' + p.name + '</strong></td>';
        for (const d of dims) {
            html += '<td style="text-align:center">' + (p.scores_detail ? p.scores_detail[d.id].toFixed(1) : '-') + '</td>';
        }
        html += '<td style="text-align:center;font-weight:700">' + (p.score ? p.score.toFixed(1) : '-') + '</td>';
        html += '</tr>';
    }
    html += '</tbody></table>';
    document.getElementById('categoryModalBody').innerHTML = html;
    document.getElementById('categoryModal').style.display = 'flex';
}

function closeCategoryModal() {
    document.getElementById('categoryModal').style.display = 'none';
}

// ==================== 维度矩阵 ====================
function initDimensionCheckboxes() {
    const container = document.getElementById('dimCategoryCheckboxes');
    container.innerHTML = DATA.categories.map(cat =>
        '<label class="checked" data-cat="' + cat.id + '"><input type="checkbox" checked onchange="toggleDimCategory(\'' + cat.id + '\',this)">' + cat.name + '</label>'
    ).join('');
    selectedDims = DATA.categories.map(c => c.id);
}

function toggleDimCategory(catId, checkbox) {
    const label = checkbox.parentElement;
    if (checkbox.checked) {
        label.classList.add('checked');
        if (!selectedDims.includes(catId)) selectedDims.push(catId);
    } else {
        label.classList.remove('checked');
        selectedDims = selectedDims.filter(c => c !== catId);
    }
    renderDimensionMatrix();
}

function renderDimensionMatrix() {
    const table = document.getElementById('dimensionMatrix');
    const dims = DATA.dimensions;
    const cats = DATA.categories.filter(c => selectedDims.includes(c.id));

    // Header
    let theadHtml = '<tr><th class="col-dim">对比维度</th>';
    for (const cat of cats) {
        theadHtml += '<th>' + cat.icon + ' ' + cat.name + '</th>';
    }
    theadHtml += '</tr>';
    table.querySelector('thead').innerHTML = theadHtml;

    // Body
    let bodyHtml = '';
    for (const dim of dims) {
        bodyHtml += '<tr><td class="col-dim"><strong>' + dim.icon + ' ' + dim.name + '</strong><br><span class="text-secondary text-sm">' + dim.desc + '</span></td>';
        if (cats.length === 0) {
            bodyHtml += '<td class="text-secondary">请选择至少一个品类</td>';
        } else {
            for (const cat of cats) {
                // Average score for this dimension across products in category
                let avg = 0;
                let count = 0;
                for (const pid of cat.products) {
                    const p = DATA.products[pid];
                    if (p && p.scores_detail && p.scores_detail[dim.id] !== undefined) {
                        avg += p.scores_detail[dim.id];
                        count++;
                    }
                }
                avg = count > 0 ? avg / count : 0;
                const pct = Math.round(avg * 20);
                bodyHtml += '<td><div class="dim-bar"><span class="dim-score">' + avg.toFixed(1) + '</span><div class="dim-bar-fill" style="width:' + pct + 'px"></div></div></td>';
            }
        }
        bodyHtml += '</tr>';
    }
    document.getElementById('dimensionBody').innerHTML = bodyHtml;
    updateEditModeUI();
}

// ==================== 人群推荐 ====================
function renderPersonas() {
    const grid = document.getElementById('personaGrid');
    const select = document.getElementById('personaSelect');
    select.innerHTML = '<option value="all">全部人群</option>' +
        DATA.personas.map(p => '<option value="' + p.id + '">' + p.name + '</option>').join('');

    let html = '';
    for (const persona of DATA.personas) {
        html += '<div class="persona-card ' + persona.id + ' recommended" data-persona="' + persona.id + '">';
        html += '<h3>' + persona.name + '</h3>';
        html += '<p class="persona-desc">' + persona.desc + '</p>';
        html += '<div class="persona-recs">';
        for (const rec of persona.recommendations) {
            const p = DATA.products[rec.product];
            const pName = p ? p.name : rec.product;
            const isBest = rec.type === 'best';
            html += '<div class="persona-rec ' + rec.type + '">';
            html += '<span class="rec-badge ' + rec.type + '">' + (isBest ? '⭐ 首选' : '🔹 备选') + '</span>';
            html += '<h4>' + pName + '</h4>';
            html += '<p class="rec-reason">' + rec.reason + '</p>';
            html += '<div class="rec-score">匹配度: ' + rec.score.toFixed(1) + ' / 5.0</div>';
            html += '</div>';
        }
        html += '</div>';
        html += '</div>';
    }
    grid.innerHTML = html;
    updateEditModeUI();
}

function filterPersona() {
    const val = document.getElementById('personaSelect').value;
    document.querySelectorAll('.persona-card').forEach(card => {
        if (val === 'all' || card.dataset.persona === val) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

// ==================== 综合评分 & 排名 ====================
function initRadarCheckboxes() {
    const container = document.getElementById('radarProductCheckboxes');
    let html = '';
    const allProducts = [];
    for (const cat of DATA.categories) {
        for (const pid of cat.products) {
            const p = DATA.products[pid];
            if (p) allProducts.push({ id: pid, name: p.name, category: cat.name });
        }
    }
    radarProducts = allProducts.slice(0, 4).map(p => p.id);
    html = allProducts.map((p, i) => {
        const checked = i < 4 ? ' checked' : '';
        return '<label class="' + (i < 4 ? 'checked' : '') + '"><input type="checkbox" value="' + p.id + '"' + checked + ' onchange="toggleRadarProduct(this)">' + p.name + '</label>';
    }).join('');
    container.innerHTML = html;
}

function toggleRadarProduct(cb) {
    const label = cb.parentElement;
    if (cb.checked) {
        label.classList.add('checked');
        if (!radarProducts.includes(cb.value)) radarProducts.push(cb.value);
        if (radarProducts.length > 6) {
            radarProducts.shift();
            // Uncheck first checked
            const firstChecked = document.querySelector('#radarProductCheckboxes input:checked');
            if (firstChecked && radarProducts.length > 6) firstChecked.checked = false;
        }
    } else {
        label.classList.remove('checked');
        radarProducts = radarProducts.filter(p => p !== cb.value);
    }
    renderRadarChart();
}

function renderScoring() {
    renderRanking();
    renderTop3();
    renderRadarChart();
}

function renderRanking() {
    const list = document.getElementById('rankingList');
    const products = [];
    for (const cat of DATA.categories) {
        for (const pid of cat.products) {
            const p = DATA.products[pid];
            if (p) products.push({ id: pid, name: p.name, category: cat.name, score: p.score || 0 });
        }
    }
    products.sort((a, b) => b.score - a.score);

    let html = '';
    products.forEach((p, i) => {
        let rankClass = 'normal';
        if (i === 0) rankClass = 'gold';
        else if (i === 1) rankClass = 'silver';
        else if (i === 2) rankClass = 'bronze';
        const medals = ['🥇','🥈','🥉'];
        const num = i < 3 ? medals[i] : (i + 1);
        html += '<div class="ranking-item">';
        html += '<span class="rank-num ' + rankClass + '">' + num + '</span>';
        html += '<div class="rank-info"><div class="rank-name">' + p.name + '</div><div class="rank-cat">' + p.category + '</div></div>';
        html += '<span class="rank-score">' + p.score.toFixed(1) + '</span>';
        html += '</div>';
    });
    list.innerHTML = html;
}

function renderTop3() {
    const grid = document.getElementById('top3Grid');
    const dims = DATA.dimensions;
    let html = '';
    for (const dim of dims) {
        const scores = [];
        for (const cat of DATA.categories) {
            for (const pid of cat.products) {
                const p = DATA.products[pid];
                if (p && p.scores_detail && p.scores_detail[dim.id] !== undefined) {
                    scores.push({ name: p.name, score: p.scores_detail[dim.id] });
                }
            }
        }
        scores.sort((a, b) => b.score - a.score);
        const top3 = scores.slice(0, 3);
        html += '<div class="top3-card"><h4>' + dim.icon + ' ' + dim.name + '</h4><ol>';
        top3.forEach(s => html += '<li>' + s.name + ' (' + s.score.toFixed(1) + ')</li>');
        html += '</ol></div>';
    }
    grid.innerHTML = html;
}

// ==================== 雷达图 (Canvas) ====================
function renderRadarChart() {
    const canvas = document.getElementById('radarChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const dims = DATA.dimensions;
    const dimIds = dims.map(d => d.id);
    const N = dimIds.length;       // 8 dimensions
    const cx = W / 2;
    const cy = H / 2;
    const maxR = Math.min(cx, cy) - 40;

    const colors = ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4'];

    // Draw grid circles and axis
    for (let r = 1; r <= 5; r++) {
        ctx.beginPath();
        for (let i = 0; i < N; i++) {
            const angle = (Math.PI * 2 / N) * i - Math.PI / 2;
            const px = cx + Math.cos(angle) * maxR * r / 5;
            const py = cy + Math.sin(angle) * maxR * r / 5;
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.stroke();
        if (r % 2 === 0) {
            ctx.fillStyle = '#f9fafb';
            ctx.fill();
        }
    }

    // Draw axis lines
    for (let i = 0; i < N; i++) {
        const angle = (Math.PI * 2 / N) * i - Math.PI / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(angle) * maxR, cy + Math.sin(angle) * maxR);
        ctx.strokeStyle = '#d1d5db';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Label
        const lx = cx + Math.cos(angle) * (maxR + 22);
        const ly = cy + Math.sin(angle) * (maxR + 22);
        ctx.fillStyle = '#374151';
        ctx.font = 'bold 11px -apple-system, "PingFang SC", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(dims[i].icon + dims[i].name, lx, ly);
    }

    // Draw products
    const selected = radarProducts.filter(pid => DATA.products[pid]);
    selected.forEach((pid, idx) => {
        const p = DATA.products[pid];
        if (!p || !p.scores_detail) return;
        const color = colors[idx % colors.length];

        ctx.beginPath();
        for (let i = 0; i < N; i++) {
            const dimId = dimIds[i];
            const score = p.scores_detail[dimId] || 0;
            const angle = (Math.PI * 2 / N) * i - Math.PI / 2;
            const px = cx + Math.cos(angle) * maxR * score / 5;
            const py = cy + Math.sin(angle) * maxR * score / 5;
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.fillStyle = color + '20';
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Points
        for (let i = 0; i < N; i++) {
            const dimId = dimIds[i];
            const score = p.scores_detail[dimId] || 0;
            const angle = (Math.PI * 2 / N) * i - Math.PI / 2;
            const px = cx + Math.cos(angle) * maxR * score / 5;
            const py = cy + Math.sin(angle) * maxR * score / 5;
            ctx.beginPath();
            ctx.arc(px, py, 4, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
        }
    });

    // Legend
    const legendX = 20;
    let legendY = H - 20 - selected.length * 20;
    selected.forEach((pid, idx) => {
        const p = DATA.products[pid];
        const color = colors[idx % colors.length];
        ctx.fillStyle = color;
        ctx.fillRect(legendX, legendY, 12, 12);
        ctx.fillStyle = '#374151';
        ctx.font = '12px -apple-system, "PingFang SC", sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(p.name + ' (' + (p.score || 0).toFixed(1) + ')', legendX + 18, legendY + 6);
        legendY += 20;
    });
}

// ==================== 编辑模式 ====================
function toggleEditMode() {
    editMode = !editMode;
    const btn = document.getElementById('toggleEditBtn');
    const resetBtn = document.getElementById('resetDataBtn');
    if (editMode) {
        btn.textContent = '🔒 退出编辑';
        btn.classList.add('active');
        resetBtn.style.display = 'inline-block';
    } else {
        btn.textContent = '✏️ 编辑模式';
        btn.classList.remove('active');
        resetBtn.style.display = 'none';
    }
    updateEditModeUI();
}

function updateEditModeUI() {
    const container = document.querySelector('.container');
    if (editMode) {
        container.classList.add('edit-mode');
    } else {
        container.classList.remove('edit-mode');
    }
}

// ==================== 单元格编辑弹窗 ====================
function openCellEdit(pid, field) {
    if (!editMode) return;
    const p = DATA.products[pid];
    if (!p) return;
    const value = field === 'score' ? (p.score || 0) : (p[field] || '');

    let title = '编辑 ' + p.name + ' — ';
    if (field === 'score') title += '综合评分';
    else {
        const dim = DATA.dimensions.find(d => d.id === field);
        title += (dim ? dim.name : field);
    }

    document.getElementById('modalTitle').textContent = title;

    let bodyHtml = '';
    if (field === 'score') {
        bodyHtml += '<label>综合评分 (0-5)</label>';
        bodyHtml += '<input type="number" id="modalInput" value="' + value + '" min="0" max="5" step="0.1">';
        bodyHtml += '<div class="star-input" id="starInput">';
        for (let i = 1; i <= 5; i++) {
            bodyHtml += '<button type="button" class="' + (i <= value ? 'active' : '') + '" onclick="setStarRating(' + i + ')">★</button>';
        }
        bodyHtml += '</div>';
    } else {
        bodyHtml += '<label>内容</label>';
        bodyHtml += '<textarea id="modalInput" rows="4">' + escapeHtml(value) + '</textarea>';
    }

    document.getElementById('modalBody').innerHTML = bodyHtml;
    modalTarget = { pid: pid, field: field };
    document.getElementById('editModal').style.display = 'flex';

    // Star click handlers
    if (field === 'score') {
        document.querySelectorAll('#starInput button').forEach(btn => {
            btn.addEventListener('click', function() {
                const rating = parseInt(this.textContent);
                document.getElementById('modalInput').value = rating;
                document.querySelectorAll('#starInput button').forEach((b, i) => {
                    b.classList.toggle('active', i < rating);
                });
            });
        });
        document.getElementById('modalInput').addEventListener('input', function() {
            const v = parseFloat(this.value) || 0;
            document.querySelectorAll('#starInput button').forEach((b, i) => {
                b.classList.toggle('active', i < v);
            });
        });
    }
}

function setStarRating(rating) {
    document.getElementById('modalInput').value = rating;
    document.querySelectorAll('#starInput button').forEach((b, i) => {
        b.classList.toggle('active', i < rating);
    });
}

function saveModalEdit() {
    if (!modalTarget) return;
    const input = document.getElementById('modalInput');
    let value = input.value;
    const { pid, field } = modalTarget;

    if (field === 'score') {
        value = parseFloat(value) || 0;
        value = Math.max(0, Math.min(5, value));
        DATA.products[pid].score = value;
    } else {
        DATA.products[pid][field] = value;
    }

    saveData();
    closeModal();
    renderAll();
}

function closeModal() {
    document.getElementById('editModal').style.display = 'none';
    modalTarget = null;
}

// ==================== 导入导出 ====================
function exportData() {
    const blob = new Blob([JSON.stringify(DATA, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'home_ai_recommend_' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
    URL.revokeObjectURL(url);
}

function importData(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const imported = JSON.parse(e.target.result);
            if (!imported.categories || !imported.products || !imported.dimensions || !imported.personas) {
                alert('数据格式不正确，缺少必要字段 (categories/products/dimensions/personas)');
                return;
            }
            if (confirm('导入将覆盖当前所有数据，确认导入？')) {
                DATA = imported;
                saveData();
                renderAll();
                alert('数据导入成功！');
            }
        } catch (err) {
            alert('JSON 解析失败: ' + err.message);
        }
    };
    reader.readAsText(file);
    event.target.value = '';
}

// ==================== 工具函数 ====================
function escapeHtml(text) {
    if (!text && text !== 0) return '';
    const d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
}

// Click modal overlay to close
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
        closeCategoryModal();
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
        closeCategoryModal();
    }
    if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        toggleEditMode();
    }
});

