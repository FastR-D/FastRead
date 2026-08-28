import CustomLogo from '@/assets/customAI.png'
import { resolveLobeIcon, type LobeIconStyle } from './lobeIcon'

interface AILogoProps {
    name: string;               // 图标名称（区分大小写！如 OpenAI、DeepSeek）
    style?: LobeIconStyle;
    size?: number;
}

const AILogo = ({ name, style = 'Color', size = 24 }: AILogoProps) => {
    const resolved = resolveLobeIcon(name, style);
    if (!resolved) {
        if (name && name !== 'custom') {
            console.warn(`AILogo: 未匹配到图标，使用占位: ${name}`);
        }
        return (
            <span className="inline-flex items-center justify-center" style={{ width: size, height: size }}>
                <img src={CustomLogo} alt="Custom AI" style={{ width: size, height: size }} />
            </span>
        );
    }

    const { Icon, Variant } = resolved;
    if (!Variant) {
        return <Icon size={size} />;
    }

    return <Variant size={size} />;
};

export default AILogo;
