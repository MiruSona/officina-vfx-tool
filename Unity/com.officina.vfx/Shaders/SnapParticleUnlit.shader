// 파티클 중심을 PPU 격자에 스냅하는 unlit 셰이더(URP 2D 렌더러용). 블렌드는 머티리얼 속성으로 고른다.
// Custom Vertex Streams 는 Position · Color · UV · Center 순서 — 자세한 건 같은 폴더 README.md.
Shader "Officina/Vfx/SnapParticleUnlit"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _PPU ("Pixels Per Unit", Float) = 32
        _Snap ("Snap (0/1)", Float) = 1
        [Enum(UnityEngine.Rendering.BlendMode)] _SrcBlend ("Src Blend", Float) = 5
        [Enum(UnityEngine.Rendering.BlendMode)] _DstBlend ("Dst Blend", Float) = 10
        [Enum(UnityEngine.Rendering.BlendMode)] _SrcBlendAlpha ("Src Blend Alpha", Float) = 1
        [Enum(UnityEngine.Rendering.BlendMode)] _DstBlendAlpha ("Dst Blend Alpha", Float) = 10
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        Blend [_SrcBlend] [_DstBlend], [_SrcBlendAlpha] [_DstBlendAlpha]
        ZWrite Off
        Cull Off

        // LightMode 태그 없음 — 실측 판이 이 꼴로 2D 렌더러에서 그려졌다.
        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            // SRP Batcher 짝 : 셰이더 변수로 쓰는 머티리얼 속성은 전부 여기(블렌드 숫자는 렌더 상태라 뺀다).
            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                half4 _Color;
                float _PPU;
                float _Snap;
            CBUFFER_END

            #include "Packages/com.officina.vfx/Shaders/VfxSnap.hlsl"

            struct Attributes
            {
                float3 positionOS : POSITION;
                half4 color       : COLOR;
                float4 uvCenter   : TEXCOORD0; // xy = UV, zw = 입자 중심 xy
                float centerZ     : TEXCOORD1; // x = 입자 중심 z
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                half4 color       : COLOR;
                float2 uv         : TEXCOORD0;
            };

            Varyings vert(Attributes input)
            {
                Varyings o;
                float3 centerOS = float3(input.uvCenter.zw, input.centerZ);
                float3 positionWS = VfxSnapPositionWS(input.positionOS, centerOS);
                o.positionCS = TransformWorldToHClip(positionWS);
                o.color = input.color * _Color;
                o.uv = TRANSFORM_TEX(input.uvCenter.xy, _MainTex);
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                return SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv) * input.color;
            }
            ENDHLSL
        }
    }
}
