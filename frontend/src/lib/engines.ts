export interface EngineInfo {
  key: string;
  code: string;
  name: string;
  description: string;
  type: string;
  url?: string;
}

export const engines: EngineInfo[] = [
  { key: 'classifier_tmr', code: 'TM', name: 'TMR Detector', description: 'RoBERTa-based text classifier', type: 'neural', url: 'https://huggingface.co/Oxidane/tmr-ai-text-detector' },
  { key: 'classifier_remodetect', code: 'RM', name: 'ReMoDetect', description: 'DeBERTa reward model detector', type: 'neural', url: 'https://huggingface.co/hyunseoki/ReMoDetect-deberta' },
  { key: 'binoculars', code: 'BN', name: 'Binoculars', description: 'Cross-perplexity ratio test', type: 'statistical', url: 'https://arxiv.org/abs/2401.12070' },
  { key: 'fast_detectgpt', code: 'FD', name: 'Fast-DetectGPT', description: 'Perturbation-based detection', type: 'statistical', url: 'https://arxiv.org/abs/2310.05130' },
  { key: 'perplexity', code: 'PP', name: 'Perplexity', description: 'GPT-2 Medium perplexity score', type: 'statistical', url: 'https://huggingface.co/openai-community/gpt2-medium' },
  { key: 'cross_perplexity', code: 'XP', name: 'Cross-Perplexity', description: 'DistilGPT-2 cross-entropy', type: 'statistical', url: 'https://huggingface.co/distilbert/distilgpt2' },
  { key: 'classifier_fakespot', code: 'FS', name: 'Fakespot', description: 'RoBERTa AI text classifier', type: 'neural', url: 'https://huggingface.co/fakespot-ai/roberta-base-ai-text-detection-v1' },
  { key: 'classifier_e5', code: 'E5', name: 'E5-Small', description: 'E5 embedding + LoRA classifier', type: 'embedding', url: 'https://huggingface.co/MayZhou/e5-small-lora-ai-generated-detector' },
  { key: 'classifier_bert_raid', code: 'BT', name: 'BERT-tiny RAID', description: 'BERT-tiny trained on RAID dataset', type: 'neural', url: 'https://huggingface.co/ShantanuT01/BERT-tiny-RAID' },
  { key: 'classifier_openai', code: 'OA', name: 'OpenAI Detector', description: 'RoBERTa OpenAI detector', type: 'classifier', url: 'https://huggingface.co/roberta-base-openai-detector' },
  { key: 'classifier_chatgpt', code: 'CG', name: 'ChatGPT Detector', description: 'RoBERTa ChatGPT classifier', type: 'classifier', url: 'https://huggingface.co/Hello-SimpleAI/chatgpt-detector-roberta' },
  { key: 'classifier_desklib', code: 'DL', name: 'Desklib DeBERTa', description: 'DeBERTa-v3 AI text detector', type: 'neural', url: 'https://huggingface.co/desklib/ai-text-detector-v1.01' },
  { key: 'classifier_superannotate', code: 'SN', name: 'SuperAnnotate', description: 'RoBERTa-large AI detector', type: 'neural', url: 'https://huggingface.co/SuperAnnotate/ai-detector' },
  { key: 'gltr', code: 'GL', name: 'GLTR', description: 'Token probability analysis', type: 'statistical', url: 'https://arxiv.org/abs/1906.04043' },
  { key: 'log_rank', code: 'LR', name: 'Log-Rank', description: 'Token log-rank statistics', type: 'statistical', url: 'https://huggingface.co/openai-community/gpt2-medium' },
  { key: 'diveye', code: 'DE', name: 'DivEye', description: 'KL divergence analysis', type: 'statistical' },
  { key: 'burstiness', code: 'BU', name: 'Burstiness', description: 'Sentence-level variance', type: 'linguistic' },
  { key: 'linguistic', code: 'LM', name: 'Linguistic', description: 'Linguistic pattern analysis', type: 'linguistic' },
  { key: 'structural', code: 'SA', name: 'Structural', description: 'Document structure analysis', type: 'linguistic' },
  { key: 'vocabulary', code: 'VR', name: 'Vocabulary', description: 'Vocabulary richness metrics', type: 'linguistic' },
  { key: 'formulaic', code: 'FP', name: 'Formulaic', description: 'AI phrase detection', type: 'linguistic' },
  { key: 'readability', code: 'RU', name: 'Readability', description: 'Readability uniformity', type: 'linguistic' },
  { key: 'sentiment', code: 'SH', name: 'Sentiment', description: 'Sentiment consistency', type: 'linguistic' },
];

export const enginesByKey = new Map(engines.map(e => [e.key, e]));
