// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title GhostCrowToken (GCROW)
 * @notice ERC-20 token + on-chain Merkle rollup anchor for AtAA / Maz CROW Chain.
 *         Deploy to Base Sepolia (84532) for testing, then Base Mainnet (8453).
 */
contract GhostCrowToken {
    string public constant name = "GHOSTCROW";
    string public constant symbol = "GCROW";
    uint8 public constant decimals = 18;
    uint256 public immutable totalSupply;

    address public owner;
    uint256 public latestRollupBatch;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event RollupAnchored(
        uint256 indexed batchId,
        bytes32 indexed merkleRoot,
        uint256 blockCount,
        uint256 peakLibrarians,
        uint256 timestamp
    );
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "GCROW: caller is not owner");
        _;
    }

    constructor(address treasury) {
        require(treasury != address(0), "GCROW: zero treasury");
        owner = msg.sender;
        uint256 supply = 1_000_000 * 10 ** uint256(decimals);
        totalSupply = supply;
        balanceOf[treasury] = supply;
        emit Transfer(address(0), treasury, supply);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "GCROW: insufficient allowance");
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - value;
        }
        _transfer(from, to, value);
        return true;
    }

    function anchorRollupRoot(
        bytes32 merkleRoot,
        uint256 blockCount,
        uint256 peakLibrarians
    ) external onlyOwner returns (uint256 batchId) {
        batchId = ++latestRollupBatch;
        emit RollupAnchored(batchId, merkleRoot, blockCount, peakLibrarians, block.timestamp);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "GCROW: zero owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _transfer(address from, address to, uint256 value) internal {
        require(to != address(0), "GCROW: zero recipient");
        require(balanceOf[from] >= value, "GCROW: insufficient balance");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }
}
