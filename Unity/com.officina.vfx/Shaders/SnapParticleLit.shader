// 2D 빛을 받는 스냅 파티클 셰이더(손 HLSL). 패스 짜임은 URP Sprite-Lit-Default 를 따르고 정점에 스냅을 넣는다.
// Custom Vertex Streams 는 Unlit 과 같이 Position · Color · UV · Center. 블렌드는 알파 고정.
Shader "Officina/Vfx/SnapParticleLit"
{
    Properties
    {
        _MainTex ("Diffuse", 2D) = "white" {}
        _MaskTex ("Mask", 2D) = "white" {}
        _NormalMap ("Normal Map", 2D) = "bump" {}
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _PPU ("Pixels Per Unit", Float) = 32
        _Snap ("Snap (0/1)", Float) = 1
    }

    SubShader
    {
        Tags { "Queue" = "Transparent" "RenderType" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        // 알파 채널은 One OneMinusSrcAlpha — 투명 배경에 그릴 때 알파가 a² 로 줄지 않게 한다.
        Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
        ZWrite Off
        Cull Off

        // 세 패스가 같이 쓰는 것. SRP Batcher 는 패스마다 CBUFFER 꼴이 같아야 해서 여기 한 번만 둔다.
        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/Core2D.hlsl"

        TEXTURE2D(_MainTex);
        SAMPLER(sampler_MainTex);
        TEXTURE2D(_MaskTex);
        SAMPLER(sampler_MaskTex);
        TEXTURE2D(_NormalMap);
        SAMPLER(sampler_NormalMap);

        CBUFFER_START(UnityPerMaterial)
            float4 _MainTex_ST;
            half4 _Color;
            float _PPU;
            float _Snap;
        CBUFFER_END

        #include "Packages/com.officina.vfx/Shaders/VfxSnap.hlsl"

        // 파티클 스트림 : TEXCOORD0 = (UV.xy, 중심.xy) · TEXCOORD1.x = 중심.z
        struct Attributes
        {
            float3 positionOS : POSITION;
            half4 color       : COLOR;
            float4 uvCenter   : TEXCOORD0;
            float centerZ     : TEXCOORD1;
        };

        float4 VfxSnapPositionCS(Attributes input)
        {
            float3 centerOS = float3(input.uvCenter.zw, input.centerZ);
            return TransformWorldToHClip(VfxSnapPositionWS(input.positionOS, centerOS));
        }
        ENDHLSL

        // 2D 렌더러가 빛을 합성해 그리는 패스.
        Pass
        {
            Tags { "LightMode" = "Universal2D" }

            HLSLPROGRAM
            #pragma vertex LitVertex
            #pragma fragment LitFragment

            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/ShapeLightShared.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/CombinedShapeLightShared.hlsl"

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                half2 lightingUV  : TEXCOORD1;
                half4 color       : COLOR;
            };

            Varyings LitVertex(Attributes input)
            {
                Varyings o = (Varyings)0;
                o.positionCS = VfxSnapPositionCS(input);
                o.uv = TRANSFORM_TEX(input.uvCenter.xy, _MainTex);
                // 빛 텍스처는 화면 좌표로 읽는다(Lit2DCommon 의 CommonLitVertex 와 같은 식).
                o.lightingUV = half2(ComputeScreenPos(o.positionCS / o.positionCS.w).xy);
                o.color = input.color * _Color;
                return o;
            }

            half4 LitFragment(Varyings input) : SV_Target
            {
                const half4 main = input.color * SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                const half4 mask = SAMPLE_TEXTURE2D(_MaskTex, sampler_MaskTex, input.uv);
                const half3 normalTS = UnpackNormal(SAMPLE_TEXTURE2D(_NormalMap, sampler_NormalMap, input.uv));

                SurfaceData2D surfaceData;
                InputData2D inputData;
                InitializeSurfaceData(main.rgb, main.a, mask, normalTS, surfaceData);
                InitializeInputData(input.uv, input.lightingUV, inputData);
                return CombinedShapeLightShared(surfaceData, inputData);
            }
            ENDHLSL
        }

        // 노멀 맵 빛을 쓸 때 2D 렌더러가 노멀 버퍼를 채우는 패스.
        Pass
        {
            Tags { "LightMode" = "NormalsRendering" }

            HLSLPROGRAM
            #pragma vertex NormalsVertex
            #pragma fragment NormalsFragment

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                half4 color       : COLOR;
            };

            Varyings NormalsVertex(Attributes input)
            {
                Varyings o = (Varyings)0;
                o.positionCS = VfxSnapPositionCS(input);
                o.uv = TRANSFORM_TEX(input.uvCenter.xy, _MainTex);
                o.color = input.color * _Color;
                return o;
            }

            half4 NormalsFragment(Varyings input) : SV_Target
            {
                const half4 main = input.color * SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                const half3 normalTS = UnpackNormal(SAMPLE_TEXTURE2D(_NormalMap, sampler_NormalMap, input.uv));

                // 파티클엔 노멀·탄젠트 스트림이 없어 스프라이트와 같은 고정 틀(카메라를 보는 면)을 쓴다.
                const half3 tangentWS = half3(1, 0, 0);
                const half3 bitangentWS = half3(0, 1, 0);
                const half3 normalWS = half3(0, 0, -1);
                half3 n = TransformTangentToWorld(normalTS, half3x3(tangentWS, bitangentWS, normalWS));

                half4 normalColor;
                normalColor.rgb = 0.5 * (n + 1);
                normalColor.a = main.a;
                return normalColor;
            }
            ENDHLSL
        }

        // 2D 렌더러가 아닌 URP 렌더러에서 쓰는 대비 패스(빛 없이 텍스처 × 색).
        Pass
        {
            Tags { "LightMode" = "UniversalForward" "Queue" = "Transparent" "RenderType" = "Transparent" }

            HLSLPROGRAM
            #pragma vertex UnlitVertex
            #pragma fragment UnlitFragment

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                half4 color       : COLOR;
            };

            Varyings UnlitVertex(Attributes input)
            {
                Varyings o = (Varyings)0;
                o.positionCS = VfxSnapPositionCS(input);
                o.uv = TRANSFORM_TEX(input.uvCenter.xy, _MainTex);
                o.color = input.color * _Color;
                return o;
            }

            half4 UnlitFragment(Varyings input) : SV_Target
            {
                return input.color * SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
            }
            ENDHLSL
        }
    }
}
