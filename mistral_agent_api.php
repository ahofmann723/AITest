<?php
/**
 * Mistral AI Studio Agent API Client
 * 
 * This script sends a request to a specific agent in Mistral AI Studio
 * using the Conversations API with an agent ID.
 */

// Configuration - REPLACE THESE VALUES
define('MISTRAL_API_KEY', 'your-mistral-api-key-here');
define('AGENT_ID', 'your-agent-id-here'); // Your Mistral AI Studio agent ID
define('MISTRAL_API_URL', 'https://api.mistral.ai/v1/conversations');

/**
 * Send a message to a specific agent in Mistral AI Studio
 */
function sendToAgent($agentId, $message, $model = null, $temperature = 0.7, $maxTokens = 150) {
    
    // Build the request payload for an agent
    $payload = [
        'agent_id' => $agentId,
        'model' => $model, // Optional: can override agent's default model
        'messages' => [
            [
                'role' => 'user',
                'content' => $message,
            ]
        ],
        'temperature' => $temperature,
        'max_tokens' => $maxTokens,
        'top_p' => 1.0,
    ];
    
    // If no model specified, remove it from payload (agent will use its default)
    if ($model === null) {
        unset($payload['model']);
    }
    
    // Headers
    $headers = [
        'Content-Type: application/json',
        'Accept: application/json',
        'Authorization: Bearer ' . MISTRAL_API_KEY,
    ];
    
    // Initialize cURL
    $ch = curl_init(MISTRAL_API_URL);
    
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 60, // Longer timeout for agent processing
    ]);
    
    // Execute request
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    $responseHeaders = curl_getinfo($ch, CURLINFO_HEADER_OUT);
    curl_close($ch);
    
    return [
        'success' => $error === '',
        'http_code' => $httpCode,
        'response' => $response,
        'error' => $error,
        'request_payload' => $payload,
        'request_headers' => $headers,
    ];
}

/**
 * Send a message to an agent with partially base64-encoded content
 */
function sendToAgentWithPartialEncoding($agentId, $message, $encodeFromIndex = 0) {
    
    // Partially encode the message
    $firstPart = substr($message, 0, $encodeFromIndex);
    $secondPart = substr($message, $encodeFromIndex);
    $encodedPart = base64_encode($secondPart);
    
    $encodedMessage = $firstPart . '[BASE64:' . $encodedPart . ']';
    
    // Build the request payload
    $payload = [
        'agent_id' => $agentId,
        'messages' => [
            [
                'role' => 'user',
                'content' => $encodedMessage,
                'metadata' => [
                    'encoding' => 'partial_base64',
                    'encode_start_index' => $encodeFromIndex,
                    'original_length' => strlen($message),
                ]
            ]
        ],
        'temperature' => 0.7,
        'max_tokens' => 150,
    ];
    
    // Headers
    $headers = [
        'Content-Type: application/json',
        'Accept: application/json',
        'Authorization: Bearer ' . MISTRAL_API_KEY,
        'X-Agent-Encoding: partial_base64', // Custom header for encoding info
    ];
    
    // Initialize cURL
    $ch = curl_init(MISTRAL_API_URL);
    
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 60,
    ]);
    
    // Execute request
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    return [
        'success' => $error === '',
        'http_code' => $httpCode,
        'response' => $response,
        'error' => $error,
        'request_payload' => $payload,
        'encoded_message' => $encodedMessage,
        'original_message' => $message,
    ];
}

/**
 * Start a conversation with an agent and maintain session
 */
function startAgentConversation($agentId, $initialMessage, $conversationId = null) {
    
    $payload = [
        'agent_id' => $agentId,
        'messages' => [
            [
                'role' => 'user',
                'content' => $initialMessage,
            ]
        ],
        'temperature' => 0.7,
        'max_tokens' => 150,
    ];
    
    // If conversation ID is provided, include it for session continuity
    if ($conversationId) {
        $payload['conversation_id'] = $conversationId;
    }
    
    $headers = [
        'Content-Type: application/json',
        'Accept: application/json',
        'Authorization: Bearer ' . MISTRAL_API_KEY,
    ];
    
    $ch = curl_init(MISTRAL_API_URL);
    
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 60,
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    $result = [
        'success' => $error === '',
        'http_code' => $httpCode,
        'response' => $response,
        'error' => $error,
        'request_payload' => $payload,
    ];
    
    // Try to extract conversation ID from response if available
    if ($result['success']) {
        $responseData = json_decode($response, true);
        if (isset($responseData['conversation_id'])) {
            $result['conversation_id'] = $responseData['conversation_id'];
        }
    }
    
    return $result;
}

// Example Usage
echo "=== Mistral AI Studio Agent API Client ===\n\n";

// Configuration check
echo "Configuration:\n";
echo "  API Key: " . (MISTRAL_API_KEY === 'your-mistral-api-key-here' ? 'NOT SET' : 'SET') . "\n";
echo "  Agent ID: " . (AGENT_ID === 'your-agent-id-here' ? 'NOT SET' : 'SET') . "\n\n";

// Sample message
$sampleMessage = "Hello Agent! I need help with a PHP script that uses the Mistral API.";

// Example 1: Basic agent call (commented out for safety)
/*
echo "Example 1: Basic Agent Call\n";
echo "Message: $sampleMessage\n\n";

$result = sendToAgent(AGENT_ID, $sampleMessage);

if ($result['success']) {
    echo "✓ Request successful!\n";
    echo "HTTP Code: {$result['http_code']}\n";
    
    $responseData = json_decode($result['response'], true);
    if (json_last_error() === JSON_ERROR_NONE) {
        echo "Response:\n";
        echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
        
        // Extract and display the agent's response
        if (isset($responseData['choices'][0]['message']['content'])) {
            echo "\nAgent Response:\n";
            echo "----------------------------------------\n";
            echo $responseData['choices'][0]['message']['content'] . "\n";
        }
    } else {
        echo "Raw Response: {$result['response']}\n";
    }
} else {
    echo "✗ Request failed:\n";
    echo "Error: {$result['error']}\n";
    echo "HTTP Code: {$result['http_code']}\n";
}

echo "\n";
*/

// Example 2: Agent call with partial base64 encoding (commented out for safety)
/*
echo "Example 2: Agent Call with Partial Base64 Encoding\n";
echo "Original Message: $sampleMessage\n";

$result = sendToAgentWithPartialEncoding(AGENT_ID, $sampleMessage, 20);

if ($result['success']) {
    echo "✓ Request successful!\n";
    echo "Encoded Message: {$result['encoded_message']}\n";
    echo "HTTP Code: {$result['http_code']}\n";
    
    $responseData = json_decode($result['response'], true);
    if (json_last_error() === JSON_ERROR_NONE) {
        echo "Response:\n";
        echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
    } else {
        echo "Raw Response: {$result['response']}\n";
    }
} else {
    echo "✗ Request failed:\n";
    echo "Error: {$result['error']}\n";
}

echo "\n";
*/

// Example 3: Start a conversation session (commented out for safety)
/*
echo "Example 3: Start Conversation with Agent\n";

$result = startAgentConversation(AGENT_ID, $sampleMessage);

if ($result['success']) {
    echo "✓ Conversation started!\n";
    echo "HTTP Code: {$result['http_code']}\n";
    
    if (isset($result['conversation_id'])) {
        echo "Conversation ID: {$result['conversation_id']}\n";
    }
    
    $responseData = json_decode($result['response'], true);
    if (json_last_error() === JSON_ERROR_NONE) {
        echo "Response:\n";
        echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
    } else {
        echo "Raw Response: {$result['response']}\n";
    }
} else {
    echo "✗ Failed to start conversation:\n";
    echo "Error: {$result['error']}\n";
}
*/

// Display sample request payloads
echo "=== Sample Request Payloads ===\n\n";

echo "1. Basic Agent Request:\n";
$basicPayload = [
    'agent_id' => AGENT_ID,
    'messages' => [
        [
            'role' => 'user',
            'content' => $sampleMessage,
        ]
    ],
    'temperature' => 0.7,
    'max_tokens' => 150,
];
echo json_encode($basicPayload, JSON_PRETTY_PRINT) . "\n\n";

echo "2. Agent Request with Partial Base64 Encoding:\n";
$firstPart = substr($sampleMessage, 0, 20);
$secondPart = substr($sampleMessage, 20);
$encodedPart = base64_encode($secondPart);
$encodedPayload = [
    'agent_id' => AGENT_ID,
    'messages' => [
        [
            'role' => 'user',
            'content' => $firstPart . '[BASE64:' . $encodedPart . ']',
            'metadata' => [
                'encoding' => 'partial_base64',
                'encode_start_index' => 20,
                'original_length' => strlen($sampleMessage),
            ]
        ]
    ],
    'temperature' => 0.7,
    'max_tokens' => 150,
];
echo json_encode($encodedPayload, JSON_PRETTY_PRINT) . "\n\n";

echo "3. Conversation Start Request:\n";
$conversationPayload = [
    'agent_id' => AGENT_ID,
    'messages' => [
        [
            'role' => 'user',
            'content' => $sampleMessage,
        ]
    ],
    'temperature' => 0.7,
    'max_tokens' => 150,
];
echo json_encode($conversationPayload, JSON_PRETTY_PRINT) . "\n\n";

echo "=== How to Use ===\n";
echo "1. Replace 'your-mistral-api-key-here' with your actual Mistral API key\n";
echo "2. Replace 'your-agent-id-here' with your Mistral AI Studio agent ID\n";
echo "3. Uncomment the example sections above to test\n";
echo "4. The agent ID can be found in your Mistral AI Studio dashboard\n";
echo "5. For conversation continuity, use the conversation_id from the first response in subsequent requests\n";

?>